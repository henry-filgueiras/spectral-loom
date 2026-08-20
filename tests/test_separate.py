"""Tests for the separation stage's decisions, refusals, and cache.

Everything here runs without torch, without weights and without audio, because
everything worth testing about this stage happens before a weight is loaded or
after the files are already on disk. The inference itself is `needs_model` and
lives outside the default suite by `archaeology/decisions/0007`.

Three properties get most of the attention.

**The precondition is the accepted hash, never the path.** A directory named
after a specimen is not evidence that a person heard what is in it.

**A cache hit is verified, not assumed.** Matching keys are not enough: a
partial run, a deleted stem, or a file that changed since the manifest was
written must all miss, and the miss must say why.

**Existing bytes are preserved.** A run that found something unexpected where
its output goes stops, and `--force` moves that something aside rather than
deleting it.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from spectral_loom.cabinet import Cabinet, load_repository_cabinet
from spectral_loom.contracts import CriterionResponse, SeparationManifest
from spectral_loom.hashing import hash_bytes
from spectral_loom.review import GATE_2_CRITERIA, build_review, review_path, write_review
from spectral_loom.separate import (
    DEMUCS_PARAMETERS,
    SeparationError,
    cache_miss_reason,
    compute_cache_key,
    load_manifest,
    plan,
    promote,
    superseded_path,
    workspace,
    write_manifest,
)
from tests.test_review import manifest as generation_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The real cabinet, because the identities this stage pins are the point and a
#: fixture cabinet would test a fiction.
CABINET: Cabinet = load_repository_cabinet(REPO_ROOT)

SPECIMEN = "sparse-funk-exposed-bass"
AUDIO = b"RIFF" + b"\x00" * 64
AUDIO_HASH = hash_bytes(AUDIO)
OTHER_AUDIO = b"RIFF" + b"\x01" * 64


# ---------------------------------------------------------------------------
# A repository-shaped fixture: generated audio, a review, and pinned weights.
# ---------------------------------------------------------------------------


def build_repository(
    root: Path, *, audio: bytes = AUDIO, accepted: bool = True, reviewed: bool = True
) -> Path:
    """Everything `plan` reads, and nothing it does not.

    The weights directory holds only `htdemucs.yaml` — the bag definition, which
    is genuinely read before inference — and not the eighty megabytes beside it,
    because none of these tests loads a model.
    """
    (root / "model-cabinet.toml").write_text(
        (REPO_ROOT / "model-cabinet.toml").read_text(), encoding="utf-8"
    )

    generated = root / "corpus/generated" / SPECIMEN
    generated.mkdir(parents=True)
    (generated / "source.wav").write_bytes(audio)

    digest = hash_bytes(audio)
    document = generation_manifest(digest)
    (generated / "generation-manifest.json").write_text(
        json.dumps(document.model_dump(mode="json"), indent=2), encoding="utf-8"
    )

    if reviewed:
        review = build_review(
            document,
            manifest_bytes=b"{}",
            cabinet_bytes=b"",
            reviewer="Henry",
            reviewed_on=date(2026, 8, 20),
            responses={c.id: CriterionResponse.YES for c in GATE_2_CRITERIA},
            accepted=accepted,
        )
        write_review(review_path(root, SPECIMEN, digest), review)

    entry = CABINET.entry["demucs"]
    weights = root / "models/demucs" / entry.assets[0].revision
    weights.mkdir(parents=True)
    (weights / "htdemucs.yaml").write_text("models: [955717e8]\n", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Planning and refusals.
# ---------------------------------------------------------------------------


def test_a_plan_resolves_the_pinned_identities(tmp_path: Path) -> None:
    build_repository(tmp_path)
    prepared = plan(SPECIMEN, CABINET, tmp_path)

    asset = CABINET.entry["demucs"].assets[0]
    assert prepared.source_hash == AUDIO_HASH
    assert prepared.model_signatures == ["955717e8"]
    assert asset.revision in prepared.tool_revision
    assert "demucs==4.1.0" in prepared.tool_revision
    assert prepared.tool == "demucs.apply.apply_model"
    assert prepared.parameters == DEMUCS_PARAMETERS


def test_shifts_stay_at_zero_because_upstream_shifts_are_random() -> None:
    """Not a style choice: shifts > 0 draws from the unseeded global RNG."""
    assert DEMUCS_PARAMETERS["shifts"] == 0


def test_planning_refuses_audio_no_one_has_reviewed(tmp_path: Path) -> None:
    build_repository(tmp_path, reviewed=False)
    with pytest.raises(SeparationError, match="Gate 2 is passed by a human listening"):
        plan(SPECIMEN, CABINET, tmp_path)


def test_planning_refuses_a_different_rendering_of_a_reviewed_specimen(tmp_path: Path) -> None:
    """The refusal this stage exists to make.

    A review is on disk, the directory name matches, and the bytes are not the
    ones anybody heard.
    """
    build_repository(tmp_path)
    (tmp_path / "corpus/generated" / SPECIMEN / "source.wav").write_bytes(OTHER_AUDIO)

    with pytest.raises(SeparationError) as caught:
        plan(SPECIMEN, CABINET, tmp_path)
    message = str(caught.value)
    assert hash_bytes(OTHER_AUDIO) in message
    assert AUDIO_HASH in message


def test_planning_refuses_bytes_a_human_rejected(tmp_path: Path) -> None:
    build_repository(tmp_path, accepted=False)
    with pytest.raises(SeparationError, match="did NOT accept"):
        plan(SPECIMEN, CABINET, tmp_path)


def test_planning_refuses_when_the_weights_are_not_on_this_machine(tmp_path: Path) -> None:
    build_repository(tmp_path)
    entry = CABINET.entry["demucs"]
    for item in (tmp_path / "models/demucs" / entry.assets[0].revision).iterdir():
        item.unlink()
    (tmp_path / "models/demucs" / entry.assets[0].revision).rmdir()

    with pytest.raises(SeparationError, match="does not download"):
        plan(SPECIMEN, CABINET, tmp_path)


def test_planning_refuses_when_there_is_no_audio(tmp_path: Path) -> None:
    build_repository(tmp_path)
    (tmp_path / "corpus/generated" / SPECIMEN / "source.wav").unlink()
    with pytest.raises(SeparationError, match="does not generate one"):
        plan(SPECIMEN, CABINET, tmp_path)


# ---------------------------------------------------------------------------
# The cache key.
# ---------------------------------------------------------------------------


def test_the_cache_key_covers_everything_that_changes_the_result(tmp_path: Path) -> None:
    build_repository(tmp_path)
    inputs = plan(SPECIMEN, CABINET, tmp_path).cache_key_inputs
    asset = CABINET.entry["demucs"].assets[0]

    assert inputs["source_hash"] == AUDIO_HASH
    assert inputs["weights_revision"] == asset.revision
    assert inputs["code"] == "demucs==4.1.0"
    assert inputs["code_sha256"] == CABINET.entry["demucs"].code.sha256
    assert inputs["bag_definition"] == {"models": ["955717e8"]}
    assert inputs["parameters"] == DEMUCS_PARAMETERS
    assert inputs["device"] == CABINET.runtime.accelerator


def test_the_backend_is_part_of_the_key(tmp_path: Path) -> None:
    """The same weights on MPS and on CPU are not the same result."""
    build_repository(tmp_path)
    on_mps = plan(SPECIMEN, CABINET, tmp_path, device="mps").cache_key
    on_cpu = plan(SPECIMEN, CABINET, tmp_path, device="cpu").cache_key
    assert on_mps != on_cpu


def test_the_key_does_not_depend_on_dictionary_ordering() -> None:
    first = compute_cache_key({"a": 1, "b": {"x": 1, "y": 2}})
    second = compute_cache_key({"b": {"y": 2, "x": 1}, "a": 1})
    assert first == second


# ---------------------------------------------------------------------------
# Reuse, and what must not be mistaken for it.
# ---------------------------------------------------------------------------


def separation_manifest(prepared: Any, root: Path) -> SeparationManifest:
    """A manifest describing files this helper actually writes.

    Written rather than faked, because every miss reason below is about the
    relationship between a document and bytes on disk, and a fixture that had
    no bytes could not exercise any of them.
    """
    prepared.output_dir.mkdir(parents=True, exist_ok=True)
    (prepared.output_dir / "diagnostics").mkdir(exist_ok=True)

    stems: list[dict[str, Any]] = []
    for index, name in enumerate(["drums", "bass", "other", "vocals"]):
        payload = f"stem-{name}".encode() * (index + 1)
        target = prepared.output_dir / f"{name}.wav"
        target.write_bytes(payload)
        stems.append(
            {
                "model_output": name,
                "audio": {
                    "path": prepared.relative(target),
                    "hash": hash_bytes(payload),
                    "duration_s": 45.0,
                    "sample_rate_hz": 44100,
                    "channels": 2,
                    "peak": 0.9,
                    "rms": 0.1,
                },
                "clipped_samples": 0,
                "non_finite_samples": 0,
            }
        )

    return SeparationManifest.model_validate(
        {
            "specimen_id": SPECIMEN,
            "source_audio": {
                "hash": prepared.source_hash,
                "duration_s": 45.0,
                "sample_rate_hz": 48000,
                "channels": 2,
            },
            "source_path": prepared.relative(prepared.source_path),
            "review_hash": prepared.review_hash,
            "generation_manifest_hash": prepared.generation_manifest_hash,
            "separator": {
                "adapter": "demucs",
                "code_distribution": "demucs",
                "code_version": "4.1.0",
                "code_sha256": CABINET.entry["demucs"].code.sha256,
                "loaded_with": "demucs.hf.load_safetensors_model",
                "applied_with": "demucs.apply.apply_model",
                "weights_repo": "adefossez/HTDemucs",
                "weights_revision": CABINET.entry["demucs"].assets[0].revision,
                "weights_variant": "htdemucs",
                "model_signatures": ["955717e8"],
                "model_sample_rate_hz": 44100,
                "model_audio_channels": 2,
                "sources": ["drums", "bass", "other", "vocals"],
            },
            "stems": stems,
            "diagnostics": [],
            "cache_key": prepared.cache_key,
            "cache_key_inputs": prepared.cache_key_inputs,
            "warnings": [],
            "provenance": [
                {
                    "stage": "separate",
                    "tool": prepared.tool,
                    "tool_revision": prepared.tool_revision,
                    "truth_layer": "inferred",
                    "input_hashes": {"source": prepared.source_hash},
                    "parameters": dict(DEMUCS_PARAMETERS),
                    "output_hashes": {s["model_output"]: s["audio"]["hash"] for s in stems},
                    "runtime": "cpython3.11 darwin-arm64 mps",
                    "duration_ms": 41230,
                }
            ],
        }
    )


def prepared_with_result(tmp_path: Path) -> tuple[Any, SeparationManifest]:
    build_repository(tmp_path)
    prepared = plan(SPECIMEN, CABINET, tmp_path)
    manifest = separation_manifest(prepared, tmp_path)
    write_manifest(prepared.manifest_path, manifest)
    return prepared, manifest


def test_a_complete_matching_result_is_a_hit(tmp_path: Path) -> None:
    prepared, manifest = prepared_with_result(tmp_path)
    assert cache_miss_reason(prepared, manifest) is None


def test_a_changed_key_is_a_miss_that_says_so(tmp_path: Path) -> None:
    _, manifest = prepared_with_result(tmp_path)
    other = plan(SPECIMEN, CABINET, tmp_path, device="cpu")
    reason = cache_miss_reason(other, manifest)
    assert reason is not None
    assert "cache key differs" in reason


def test_a_missing_output_is_not_a_hit(tmp_path: Path) -> None:
    """A partial prior run is the failure this check exists for."""
    prepared, manifest = prepared_with_result(tmp_path)
    (tmp_path / manifest.stems[1].audio.path).unlink()

    reason = cache_miss_reason(prepared, manifest)
    assert reason is not None
    assert "missing" in reason
    assert "bass" in reason


def test_an_output_that_changed_since_the_manifest_is_not_a_hit(tmp_path: Path) -> None:
    prepared, manifest = prepared_with_result(tmp_path)
    (tmp_path / manifest.stems[0].audio.path).write_bytes(b"something else")

    reason = cache_miss_reason(prepared, manifest)
    assert reason is not None
    assert "no longer hashes" in reason


def test_an_internally_inconsistent_manifest_is_not_a_hit(tmp_path: Path) -> None:
    prepared, manifest = prepared_with_result(tmp_path)
    document = manifest.model_dump(mode="json")
    document["stems"] = document["stems"][:2]
    trimmed = SeparationManifest.model_validate(document)

    reason = cache_miss_reason(prepared, trimmed)
    assert reason is not None
    assert "internally inconsistent" in reason


def test_stems_that_disagree_about_their_sample_rate_are_not_a_hit(tmp_path: Path) -> None:
    prepared, manifest = prepared_with_result(tmp_path)
    document = manifest.model_dump(mode="json")
    document["stems"][0]["audio"]["sample_rate_hz"] = 48000
    mixed = SeparationManifest.model_validate(document)

    reason = cache_miss_reason(prepared, mixed)
    assert reason is not None
    assert "sample rate" in reason


def test_a_manifest_for_other_source_bytes_is_not_a_hit(tmp_path: Path) -> None:
    prepared, manifest = prepared_with_result(tmp_path)
    document = manifest.model_dump(mode="json")
    document["source_audio"]["hash"] = hash_bytes(OTHER_AUDIO)
    other = SeparationManifest.model_validate(document)

    reason = cache_miss_reason(prepared, other)
    assert reason is not None
    assert hash_bytes(OTHER_AUDIO) in reason


def test_an_unreadable_manifest_is_an_error_with_the_path_in_it(tmp_path: Path) -> None:
    build_repository(tmp_path)
    prepared = plan(SPECIMEN, CABINET, tmp_path)
    prepared.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    prepared.manifest_path.write_text("{ not json", encoding="utf-8")

    with pytest.raises(SeparationError, match="cannot read"):
        load_manifest(prepared.manifest_path)


# ---------------------------------------------------------------------------
# Atomic promotion, and not destroying bytes.
# ---------------------------------------------------------------------------


def test_a_workspace_sits_beside_its_destination(tmp_path: Path) -> None:
    """Beside, so promotion is a rename on one filesystem rather than a copy."""
    build_repository(tmp_path)
    prepared = plan(SPECIMEN, CABINET, tmp_path)
    assert workspace(prepared).parent == prepared.output_dir.parent
    assert workspace(prepared) != prepared.output_dir


def test_promotion_preserves_whatever_was_already_there(tmp_path: Path) -> None:
    """Unexpected bytes are evidence about something, and are not deleted."""
    build_repository(tmp_path)
    prepared = plan(SPECIMEN, CABINET, tmp_path)

    prepared.output_dir.mkdir(parents=True)
    (prepared.output_dir / "bass.wav").write_bytes(b"an older separation")

    built = workspace(prepared)
    built.mkdir(parents=True)
    (built / "bass.wav").write_bytes(b"the new one")

    preserved = promote(prepared, built)
    assert preserved is not None
    assert (preserved / "bass.wav").read_bytes() == b"an older separation"
    assert (prepared.output_dir / "bass.wav").read_bytes() == b"the new one"
    assert not built.exists()


def test_successive_supersedings_do_not_collide(tmp_path: Path) -> None:
    target = tmp_path / "separation"
    target.mkdir()
    first = superseded_path(target)
    first.mkdir()
    assert superseded_path(target) != first


# ---------------------------------------------------------------------------
# What the manifest is allowed to say.
# ---------------------------------------------------------------------------


def test_a_stem_must_be_named_by_the_model_that_made_it(tmp_path: Path) -> None:
    _, manifest = prepared_with_result(tmp_path)
    document = manifest.model_dump(mode="json")
    document["stems"][0]["model_output"] = "electric-bass"

    with pytest.raises(ValidationError, match="not among the separator's own outputs"):
        SeparationManifest.model_validate(document)


def test_two_artifacts_may_not_claim_one_path(tmp_path: Path) -> None:
    _, manifest = prepared_with_result(tmp_path)
    document = manifest.model_dump(mode="json")
    document["stems"][1]["audio"]["path"] = document["stems"][0]["audio"]["path"]

    with pytest.raises(ValidationError, match="same path"):
        SeparationManifest.model_validate(document)


def test_the_producing_stage_is_inferred_and_the_measurements_are_not(tmp_path: Path) -> None:
    """HTDemucs had an opinion; the file sizes did not."""
    _, manifest = prepared_with_result(tmp_path)
    assert manifest.provenance[0].truth_layer == "inferred"
    assert manifest.stems[0].audio.duration_s == 45.0


def test_a_manifest_carries_no_human_judgement(tmp_path: Path) -> None:
    """Whether the separation is good is gate 3, and gate 3 is answered by ears.

    Asserted against the contract's own field names rather than against one
    document, so that adding an `accepted` or `quality` field to
    `SeparationManifest` fails here rather than in review.
    """
    fields = set(SeparationManifest.model_fields)
    forbidden = {"accepted", "quality", "review", "verdict", "rating", "score"}
    assert not fields & forbidden

    stem_fields = set(SeparationManifest.model_fields["stems"].annotation.__args__[0].model_fields)  # type: ignore[union-attr]
    assert "instrument" not in stem_fields, "a stem is named by its model, not by an instrument"
    assert "model_output" in stem_fields


# ---------------------------------------------------------------------------
# The real thing, deselected by default.
# ---------------------------------------------------------------------------


@pytest.mark.needs_model
def test_the_pinned_separator_actually_runs(tmp_path: Path) -> None:
    """Run the stage end to end against the real weights.

    Deselected by `pyproject.toml`'s default marker expression and never run in
    CI: it needs eighty megabytes of pinned weights and torch, and
    `archaeology/decisions/0007` keeps both out of the hermetic suite. Run it
    deliberately, against the cabinet environment::

        UV_PROJECT_ENVIRONMENT=.venv-cabinet \
            uv run --locked --extra cabinet --no-dev --with pytest \
            pytest -m needs_model

    The `--with` is what keeps `.venv-cabinet` as `bootstrap_cabinet.py env`
    built it: pytest is layered on for the run rather than installed into an
    environment that is deliberately `--no-dev`.

    It builds its own repository in a temporary directory and symlinks the real
    weights in, so it separates real audio without writing anything into the
    checkout.
    """
    import math
    import struct
    import wave

    from spectral_loom.separate import run

    audio_path = tmp_path / "tone.wav"
    rate = 48000
    with wave.open(str(audio_path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(
            b"".join(
                struct.pack(
                    "<hh",
                    int(12000 * math.sin(2 * math.pi * 82.4 * n / rate)),
                    int(9000 * math.sin(2 * math.pi * 440.0 * n / rate)),
                )
                for n in range(rate * 2)
            )
        )
    tone = audio_path.read_bytes()

    root = tmp_path / "repo"
    root.mkdir()
    build_repository(root, audio=tone)

    revision = CABINET.entry["demucs"].assets[0].revision
    weights = root / "models/demucs" / revision
    for item in weights.iterdir():
        item.unlink()
    weights.rmdir()
    weights.symlink_to(REPO_ROOT / "models/demucs" / revision, target_is_directory=True)

    prepared = plan(SPECIMEN, CABINET, root)
    manifest, produced = run(prepared)

    assert produced
    assert {s.model_output for s in manifest.stems} == {"drums", "bass", "other", "vocals"}
    assert {s.audio.sample_rate_hz for s in manifest.stems} == {
        manifest.separator.model_sample_rate_hz
    }
    for stem in manifest.stems:
        assert (root / stem.audio.path).is_file()
        assert stem.non_finite_samples == 0
    assert manifest.provenance[0].runtime is not None
    assert manifest.provenance[0].parameters["device"] in {"mps", "cpu", "cuda"}

    again, produced_again = run(prepared)
    assert not produced_again, "an unchanged request must not buy another inference run"
    assert again.cache_key == manifest.cache_key
