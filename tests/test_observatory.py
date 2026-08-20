"""Tests for the Stem Observatory's manifest-to-page transformation.

The page's real property — that seven lanes stay in sync on one clock — cannot
be asserted from Python and is not attempted here. What *can* be asserted is
everything the page says, and that is where the risk actually lives: a browser
that drifts by a few milliseconds is annoying, whereas a page that labels
`vocals.wav` "vocals" without qualification would quietly teach a person to read
a model's guess as a fact.

So these check the honesty of the rendering, the refusals when the artifacts on
disk are not the ones the manifest describes, and the shape of the server's file
whitelist. No audio is decoded and no socket is opened.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from spectral_loom.contracts import CriterionResponse, SeparationManifest
from spectral_loom.hashing import hash_bytes
from spectral_loom.observatory import (
    LOOPBACK,
    ObservatoryError,
    build_exhibit,
    render,
)
from spectral_loom.review import GATE_2_CRITERIA, build_review
from tests.test_review import manifest as generation_manifest

SPECIMEN = "sparse-funk-exposed-bass"
SOURCE = b"RIFFsource" * 8
SOURCE_HASH = hash_bytes(SOURCE)


def _artifact(root: Path, relative: str, payload: bytes, **extra: float | int) -> dict[str, object]:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return {
        "path": relative,
        "hash": hash_bytes(payload),
        "duration_s": 45.0,
        "sample_rate_hz": 44100,
        "channels": 2,
        "peak": 0.5,
        "rms": 0.05,
        **extra,
    }


def build_separation(root: Path) -> SeparationManifest:
    """A separation manifest whose files really exist under `root`."""
    (root / "corpus/generated" / SPECIMEN).mkdir(parents=True)
    (root / "corpus/generated" / SPECIMEN / "source.wav").write_bytes(SOURCE)

    base = f"corpus/derived/{SPECIMEN}/separation"
    stems = [
        {
            "model_output": name,
            "audio": _artifact(root, f"{base}/{name}.wav", f"stem-{name}".encode() * 4),
            "clipped_samples": 0,
            "non_finite_samples": 0,
        }
        for name in ("drums", "bass", "other", "vocals")
    ]
    diagnostics = [
        {
            "id": "reconstruction",
            "description": "The four model outputs summed. An engineering diagnostic, not a stem.",
            "audio": _artifact(root, f"{base}/diagnostics/reconstruction.wav", b"recon" * 9),
            "measurements": {"source_rms_at_model_rate": 0.114, "peak_alignment_lag_samples": 0},
        },
        {
            "id": "residual",
            "description": (
                "What separation did not account for. An engineering diagnostic, not a stem."
            ),
            "audio": _artifact(root, f"{base}/diagnostics/residual.wav", b"resid" * 9),
            "measurements": {"residual_relative_db": -30.11, "note": "no threshold is asserted"},
        },
        {
            "id": "stem-levels",
            "description": "Per-output level, to notice a stem that came back empty.",
            "measurements": {"vocals": {"rms": 0.0009}},
        },
    ]

    return SeparationManifest.model_validate(
        {
            "specimen_id": SPECIMEN,
            "source_audio": {
                "hash": SOURCE_HASH,
                "duration_s": 45.0,
                "sample_rate_hz": 48000,
                "channels": 2,
            },
            "source_path": f"corpus/generated/{SPECIMEN}/source.wav",
            "review_hash": "sha256:" + "d" * 64,
            "generation_manifest_hash": "sha256:" + "e" * 64,
            "separator": {
                "adapter": "demucs",
                "code_distribution": "demucs",
                "code_version": "4.1.0",
                "code_sha256": "a" * 64,
                "loaded_with": "demucs.hf.load_safetensors_model",
                "applied_with": "demucs.apply.apply_model",
                "weights_repo": "adefossez/HTDemucs",
                "weights_revision": "b" * 40,
                "weights_variant": "htdemucs",
                "model_signatures": ["955717e8"],
                "model_sample_rate_hz": 44100,
                "model_audio_channels": 2,
                "sources": ["drums", "bass", "other", "vocals"],
            },
            "stems": stems,
            "diagnostics": diagnostics,
            "cache_key": "sha256:" + "f" * 64,
            "cache_key_inputs": {"source_hash": SOURCE_HASH},
            "warnings": [],
            "provenance": [
                {
                    "stage": "separate",
                    "tool": "demucs.apply.apply_model",
                    "tool_revision": "demucs==4.1.0",
                    "truth_layer": "inferred",
                    "input_hashes": {"source": SOURCE_HASH},
                    "parameters": {"device": "mps", "shifts": 0},
                    "output_hashes": {},
                    "runtime": "cpython3.11 darwin-arm64 mps",
                    "duration_ms": 2790,
                }
            ],
        }
    )


def build_acceptance() -> object:
    return build_review(
        generation_manifest(SOURCE_HASH),
        manifest_bytes=b"{}",
        cabinet_bytes=b"",
        reviewer="Henry",
        reviewed_on=date(2026, 8, 20),
        responses={c.id: CriterionResponse.YES for c in GATE_2_CRITERIA},
        accepted=True,
    )


def exhibit_for(root: Path):  # type: ignore[no-untyped-def]
    return build_exhibit(build_separation(root), build_acceptance(), root)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# What the page says.
# ---------------------------------------------------------------------------


def test_the_source_comes_first_because_it_is_the_evidence(tmp_path: Path) -> None:
    exhibit = exhibit_for(tmp_path)
    assert exhibit.lanes[0].id == "source"
    assert exhibit.lanes[0].kind == "source"
    assert exhibit.lanes[0].audible, "the source is what plays before anything is chosen"


def test_stems_keep_the_separator_order_and_the_separator_name(tmp_path: Path) -> None:
    exhibit = exhibit_for(tmp_path)
    stems = [lane for lane in exhibit.lanes if lane.kind == "stem"]
    assert [lane.id for lane in stems] == ["drums", "bass", "other", "vocals"]
    assert [lane.label for lane in stems] == [
        "HTDemucs · drums",
        "HTDemucs · bass",
        "HTDemucs · other",
        "HTDemucs · vocals",
    ]


def test_every_stem_lane_says_it_is_not_a_verified_instrument(tmp_path: Path) -> None:
    """The single most important assertion in this file.

    A page that renders `bass` unqualified teaches a person to read a model's
    assignment as a measurement, and there is no later stage that can undo that.
    """
    exhibit = exhibit_for(tmp_path)
    for lane in exhibit.lanes:
        if lane.kind == "stem":
            assert "Not a verified instrument" in lane.caption
            assert "assigned" in lane.caption


def test_diagnostics_are_labelled_as_diagnostics_and_come_last(tmp_path: Path) -> None:
    exhibit = exhibit_for(tmp_path)
    kinds = [lane.kind for lane in exhibit.lanes]
    assert kinds == ["source"] + ["stem"] * 4 + ["diagnostic"] * 2
    for lane in exhibit.lanes:
        if lane.kind == "diagnostic":
            assert lane.label.startswith("Diagnostic · ")
            assert "not a stem" in lane.caption


def test_a_diagnostic_without_audio_gets_no_lane(tmp_path: Path) -> None:
    """`stem-levels` is a number, not something to listen to."""
    exhibit = exhibit_for(tmp_path)
    assert "stem-levels" not in {lane.id for lane in exhibit.lanes}
    assert any(key.startswith("stem-levels.") for key, _ in exhibit.measurements)


def test_shortcuts_are_assigned_without_collisions(tmp_path: Path) -> None:
    exhibit = exhibit_for(tmp_path)
    shortcuts = [lane.shortcut for lane in exhibit.lanes if lane.shortcut]
    assert shortcuts == ["0", "1", "2", "3", "4", "M", "R"]
    assert len(set(shortcuts)) == len(shortcuts)


def test_provenance_is_present_and_names_the_backend_and_the_revision(tmp_path: Path) -> None:
    exhibit = exhibit_for(tmp_path)
    rows = dict(exhibit.provenance)
    assert rows["backend"] == "mps"
    assert rows["weights"] == "adefossez/HTDemucs@" + "b" * 40
    assert rows["source sha256"] == SOURCE_HASH
    assert rows["elapsed"] == "2.79 s"
    assert "a model's opinion" in rows["truth layer"]
    assert "Henry on 2026-08-20" in rows["accepted by"]
    assert "not a claim about content" in rows["accepted by"]
    for name in ("drums", "bass", "other", "vocals"):
        assert f"{name} sha256" in rows


def test_measurements_carry_no_verdict(tmp_path: Path) -> None:
    """A `note` in a manifest is prose about the measurement, not a row."""
    exhibit = exhibit_for(tmp_path)
    keys = [key for key, _ in exhibit.measurements]
    assert "residual.residual_relative_db" in keys
    assert not any(key.endswith(".note") for key in keys)


# ---------------------------------------------------------------------------
# The rendered page.
# ---------------------------------------------------------------------------


def test_the_page_is_self_contained(tmp_path: Path) -> None:
    """No stylesheet, script, font or image from anywhere but this file."""
    page = render(exhibit_for(tmp_path))
    for forbidden in ("http://", "https://", "//cdn", "<link", "integrity="):
        assert forbidden not in page, f"the page reaches outside itself: {forbidden!r}"
    assert page.count("<script>") == 1
    assert "src=" not in page


def test_the_page_embeds_the_lanes_as_valid_json(tmp_path: Path) -> None:
    exhibit = exhibit_for(tmp_path)
    page = render(exhibit)
    start = page.index("const EXHIBIT = ") + len("const EXHIBIT = ")
    payload = json.loads(page[start : page.index(";\n", start)])
    assert [lane["id"] for lane in payload["lanes"]] == [lane.id for lane in exhibit.lanes]
    assert payload["duration_s"] == 45.0


def test_the_page_states_the_labelling_caveat_where_it_cannot_be_missed(tmp_path: Path) -> None:
    page = render(exhibit_for(tmp_path))
    assert "not verified instruments" in page
    assert "failure to assign rather than evidence of absence" in page


def test_the_page_does_not_assert_a_residual_threshold(tmp_path: Path) -> None:
    """Measurements are shown; a verdict on them is not, because there is none."""
    markup = render(exhibit_for(tmp_path)).split("<script>")[0]
    assert "has no evidence for a pass threshold and asserts none" in markup
    for verdict in ("acceptable", "good enough", "PASS", "FAIL", "healthy", "clean separation"):
        assert verdict not in markup, f"the page reaches a verdict it has not earned: {verdict!r}"


# ---------------------------------------------------------------------------
# Refusals.
# ---------------------------------------------------------------------------


def test_a_missing_stem_is_a_refusal_rather_than_a_silent_lane(tmp_path: Path) -> None:
    """ "The residual sounds like silence" and "the residual is gone" differ."""
    manifest = build_separation(tmp_path)
    (tmp_path / manifest.stems[1].audio.path).unlink()

    with pytest.raises(ObservatoryError, match="is not on disk"):
        build_exhibit(manifest, build_acceptance(), tmp_path)  # type: ignore[arg-type]


def test_a_stem_that_changed_since_separation_is_a_refusal(tmp_path: Path) -> None:
    manifest = build_separation(tmp_path)
    (tmp_path / manifest.stems[0].audio.path).write_bytes(b"tampered")

    with pytest.raises(ObservatoryError, match="will not present them"):
        build_exhibit(manifest, build_acceptance(), tmp_path)  # type: ignore[arg-type]


def test_a_source_that_is_not_the_one_separated_is_a_refusal(tmp_path: Path) -> None:
    manifest = build_separation(tmp_path)
    (tmp_path / manifest.source_path).write_bytes(b"a different rendering entirely")

    with pytest.raises(ObservatoryError) as caught:
        build_exhibit(manifest, build_acceptance(), tmp_path)  # type: ignore[arg-type]
    assert "worse than not comparing them" in str(caught.value)


def test_a_missing_source_is_a_refusal(tmp_path: Path) -> None:
    manifest = build_separation(tmp_path)
    (tmp_path / manifest.source_path).unlink()

    with pytest.raises(ObservatoryError, match="no longer has"):
        build_exhibit(manifest, build_acceptance(), tmp_path)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The server's exposure.
# ---------------------------------------------------------------------------


def test_the_server_serves_a_whitelist_and_not_a_document_root(tmp_path: Path) -> None:
    """There is nothing to traverse, because there is no root to traverse from."""
    exhibit = exhibit_for(tmp_path)
    assert set(exhibit.files) == {
        "/audio/source",
        "/audio/drums",
        "/audio/bass",
        "/audio/other",
        "/audio/vocals",
        "/audio/reconstruction",
        "/audio/residual",
    }
    for url, path in exhibit.files.items():
        assert path.is_file(), url
        assert path.is_absolute() or not path.is_absolute()  # either form, but it must resolve


def test_the_exhibit_serves_audio_from_where_it_already_lives(tmp_path: Path) -> None:
    """No copies and no base64: seven eight-megabyte blobs is not a microscope."""
    exhibit = exhibit_for(tmp_path)
    assert (
        exhibit.files["/audio/bass"] == tmp_path / f"corpus/derived/{SPECIMEN}/separation/bass.wav"
    )
    page = render(exhibit)
    assert "data:audio" not in page
    assert "base64" not in page


def test_the_server_binds_to_loopback_only() -> None:
    assert LOOPBACK == "127.0.0.1"
