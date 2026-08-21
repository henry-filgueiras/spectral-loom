"""Tests for the tracked record that a human heard one exact separation.

The same two pressures as `test_review.py`, one layer down and one turn harder.

The hash binding is harder because a separation is identified by a *directory
the next run will reuse*. `corpus/derived/<specimen>/separation/` resolves after
a re-separation on another backend, at another revision, with another parameter
— to stems nobody has heard. So the verdict is bound to the separation
manifest's own content hash and to every artifact in the exhibit, and the
compiler asks about that hash rather than about a path.

The truth-layer pressure is harder because a separation review is where a
listener's perception of a *model output* is most likely to be written down as a
fact about the recording. "Nothing meaningful was heard in `vocals`" is a report
about a model's failure to assign. "The source contained no vocals" is a claim
about music that nobody measured. The question wordings are asserted here so
that a later edit cannot quietly slide from the first into the second.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from spectral_loom.contracts import (
    CriterionResponse,
    SeparationManifest,
    SeparationReview,
    SupplementaryListening,
)
from spectral_loom.hashing import hash_bytes
from spectral_loom.review import (
    GATE_2_CRITERIA,
    GATE_3_CRITERIA,
    GATE_3_PURPOSE,
    ReviewError,
    build_separation_review,
    existing_reviews,
    existing_separation_reviews,
    load_separation_review,
    require_separation_accepted,
    review_path,
    separation_review_path,
    write_separation_review,
)
from tests.test_review import manifest as generation_manifest

SPECIMEN = "sparse-funk-exposed-bass"
SOURCE_HASH = "sha256:" + "a" * 64
REVIEW_HASH = "sha256:" + "d" * 64
GENERATION_HASH = "sha256:" + "e" * 64
MANIFEST_PATH = f"corpus/derived/{SPECIMEN}/separation/separation-manifest.json"

ALL_YES = {c.id: CriterionResponse.YES for c in GATE_3_CRITERIA}


def separation_manifest() -> SeparationManifest:
    """A manifest shaped like the real one, with four outputs and two diagnostics."""
    stems: list[dict[str, Any]] = [
        {
            "model_output": name,
            "audio": {
                "path": f"corpus/derived/{SPECIMEN}/separation/{name}.wav",
                "hash": "sha256:" + digit * 64,
                "duration_s": 45.0,
                "sample_rate_hz": 44100,
                "channels": 2,
                "peak": 0.9,
                "rms": 0.1,
            },
            "clipped_samples": 0,
            "non_finite_samples": 0,
        }
        for name, digit in zip(["drums", "bass", "other", "vocals"], "1234", strict=True)
    ]
    diagnostics: list[dict[str, Any]] = [
        {
            "id": name,
            "description": f"the {name}; an engineering diagnostic, not a stem",
            "audio": {
                "path": f"corpus/derived/{SPECIMEN}/separation/diagnostics/{name}.wav",
                "hash": "sha256:" + digit * 64,
                "duration_s": 45.0,
                "sample_rate_hz": 44100,
                "channels": 2,
                "peak": 0.9,
                "rms": 0.1,
            },
            "measurements": {},
        }
        for name, digit in zip(["reconstruction", "residual"], "56", strict=True)
    ] + [{"id": "stem-levels", "description": "levels", "audio": None, "measurements": {}}]

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
            "review_hash": REVIEW_HASH,
            "generation_manifest_hash": GENERATION_HASH,
            "separator": {
                "adapter": "demucs",
                "code_distribution": "demucs",
                "code_version": "4.1.0",
                "code_sha256": "f" * 64,
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
            "cache_key": "sha256:" + "7" * 64,
            "cache_key_inputs": {"source_hash": SOURCE_HASH},
            "warnings": [],
            "provenance": [
                {
                    "stage": "separate",
                    "tool": "demucs.apply.apply_model",
                    "tool_revision": "demucs==4.1.0 adefossez/HTDemucs@" + "b" * 40,
                    "truth_layer": "inferred",
                    "input_hashes": {"source": SOURCE_HASH},
                    "parameters": {"shifts": 0},
                    "output_hashes": {s["model_output"]: s["audio"]["hash"] for s in stems},
                    "runtime": "cpython3.11 darwin-arm64 mps",
                    "duration_ms": 2792,
                }
            ],
        }
    )


def build(
    *,
    manifest_bytes: bytes = b"{}",
    accepted: bool = True,
    responses: dict[str, CriterionResponse] | None = None,
    **kwargs: object,
) -> SeparationReview:
    return build_separation_review(
        separation_manifest(),
        manifest_path=MANIFEST_PATH,
        manifest_bytes=manifest_bytes,
        reviewer="Henry",
        reviewed_on=date(2026, 8, 20),
        responses=responses or ALL_YES,
        accepted=accepted,
        **kwargs,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# What the verdict is bound to.
# ---------------------------------------------------------------------------


def test_the_review_names_the_separation_by_its_manifest_hash() -> None:
    review = build(manifest_bytes=b'{"real": "document"}')
    assert review.separation_manifest_hash == hash_bytes(b'{"real": "document"}')
    assert review.separation_manifest_path == MANIFEST_PATH


def test_the_review_names_every_reviewed_artifact_by_hash() -> None:
    review = build()
    by_kind: dict[str, set[str]] = {}
    for artifact in review.reviewed_artifacts:
        by_kind.setdefault(artifact.kind, set()).add(artifact.name)

    assert by_kind["source"] == {"source"}
    assert by_kind["model_output"] == {"drums", "bass", "other", "vocals"}
    assert by_kind["diagnostic"] == {"reconstruction", "residual"}
    assert all(a.hash.startswith("sha256:") for a in review.reviewed_artifacts)


def test_a_diagnostic_without_audio_is_not_listed_as_reviewed() -> None:
    """Nobody listened to a number."""
    review = build()
    assert "stem-levels" not in {a.name for a in review.reviewed_artifacts}


def test_the_review_carries_the_exact_separator_identity() -> None:
    review = build()
    assert review.separator.code_version == "4.1.0"
    assert review.separator.weights_revision == "b" * 40
    assert review.separator.model_signatures == ["955717e8"]


def test_the_review_carries_the_gate_two_receipt() -> None:
    """A separation of unaccepted bytes could not have happened; this proves it."""
    assert build().specimen_review_hash == REVIEW_HASH


# ---------------------------------------------------------------------------
# What the question set may and may not claim.
# ---------------------------------------------------------------------------


def test_every_criterion_must_be_answered() -> None:
    partial = {c.id: CriterionResponse.YES for c in GATE_3_CRITERIA[:3]}
    with pytest.raises(ReviewError, match="partially examined assumption"):
        build(responses=partial)


def test_the_wording_travels_with_the_answer() -> None:
    review = build()
    asked = {c.id: c.question for c in review.review.criteria}
    for item in GATE_3_CRITERIA:
        assert asked[item.id] == item.question


def test_the_vocals_question_is_about_the_output_not_about_the_source() -> None:
    """The single most misreadable question in the set."""
    question = next(
        c.question for c in GATE_3_CRITERIA if c.id == "vocals-meaningful-content-perceived"
    )
    assert "`vocals` output" in question
    assert "source" not in question.lower()


def test_the_cymbal_question_asks_whether_it_is_answerable() -> None:
    """Not "did the model lose the cymbals", which presumes there were some."""
    item = next(c for c in GATE_3_CRITERIA if c.id == "drums-cymbal-material-sufficient-to-judge")
    assert "enough clearly audible cymbal" in item.question
    assert "not that the model failed" in item.help


def test_no_criterion_asks_the_reviewer_to_name_an_instrument_in_other() -> None:
    """`other` is a model output name. Nothing here invites renaming it."""
    for item in GATE_3_CRITERIA:
        combined = f"{item.question} {item.help}".lower()
        assert "guitar" not in combined
        assert "synth" not in combined


def test_the_purpose_refuses_to_be_widened() -> None:
    review = build()
    assert review.review.purpose == GATE_3_PURPOSE
    assert "failure to assign" in review.review.purpose
    assert "not a claim that any output is a verified instrument" in review.review.purpose


def test_unclear_is_representable() -> None:
    responses = dict(ALL_YES)
    responses["bass-leakage-perceived"] = CriterionResponse.UNCLEAR
    review = build(responses=responses)
    answer = next(c for c in review.review.criteria if c.id == "bass-leakage-perceived")
    assert answer.response is CriterionResponse.UNCLEAR


def test_a_rejection_is_representable() -> None:
    review = build(accepted=False, summary="the bass was smeared beyond use")
    assert review.review.accepted is False
    assert review.review.notes == "the bass was smeared beyond use"


def test_a_note_for_an_unknown_criterion_is_a_typo_not_a_new_question() -> None:
    with pytest.raises(ReviewError, match="no criterion named"):
        build(notes={"bass-sounds-nice": "it does"})


# ---------------------------------------------------------------------------
# Supplementary listening is context, not a reviewer.
# ---------------------------------------------------------------------------


def test_supplementary_listening_is_recorded_beside_the_review_not_inside_it() -> None:
    review = build(
        supplementary=[
            SupplementaryListening(
                listener="Lux",
                nature="reported to this project by the reviewer",
                summary="bass isolation strong; `other` holds several voices",
            )
        ]
    )
    assert review.review.reviewer == "Henry"
    assert len(review.supplementary) == 1
    assert review.supplementary[0].listener == "Lux"


def test_a_review_with_no_supplementary_listening_is_normal() -> None:
    assert build().supplementary == []


# ---------------------------------------------------------------------------
# The contract's own refusals.
# ---------------------------------------------------------------------------


def test_a_review_that_skipped_an_output_is_not_a_verdict() -> None:
    review = build()
    document = review.model_dump(mode="json")
    document["reviewed_artifacts"] = [
        a for a in document["reviewed_artifacts"] if a["name"] != "vocals"
    ]
    with pytest.raises(ValueError, match="was not reviewed"):
        SeparationReview.model_validate(document)


def test_a_review_of_only_diagnostics_is_a_review_of_arithmetic() -> None:
    review = build()
    document = review.model_dump(mode="json")
    document["reviewed_artifacts"] = [
        a for a in document["reviewed_artifacts"] if a["kind"] == "diagnostic"
    ]
    with pytest.raises(ValueError, match="review of arithmetic"):
        SeparationReview.model_validate(document)


# ---------------------------------------------------------------------------
# Finding it again, and refusing to.
# ---------------------------------------------------------------------------


def write(root: Path, review: SeparationReview) -> Path:
    target = separation_review_path(root, SPECIMEN, review.separation_manifest_hash)
    write_separation_review(target, review)
    return target


def test_a_written_review_round_trips(tmp_path: Path) -> None:
    review = build()
    path = write(tmp_path, review)
    assert load_separation_review(path) == review


def test_the_file_is_sorted_and_newline_terminated(tmp_path: Path) -> None:
    path = write(tmp_path, build())
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text)["schema_id"] == "spectral-loom/separation-review"


def test_a_separation_review_is_not_mistaken_for_a_specimen_review(tmp_path: Path) -> None:
    """The two live in one directory and are globbed for separately.

    A filename that matched both patterns would let `require_accepted` try to
    parse a separation review as a specimen review, which is the kind of failure
    that shows up as an unreadable-file error weeks later.
    """
    from spectral_loom.contracts import Provenance, SourceAudio  # noqa: F401
    from spectral_loom.review import build_review, write_review

    specimen = build_review(
        generation_manifest(SOURCE_HASH),
        manifest_bytes=b"{}",
        cabinet_bytes=b"",
        reviewer="Henry",
        reviewed_on=date(2026, 8, 20),
        responses={c.id: CriterionResponse.YES for c in GATE_2_CRITERIA},
        accepted=True,
    )
    write_review(review_path(tmp_path, SPECIMEN, SOURCE_HASH), specimen)
    write(tmp_path, build())

    assert [p.name for p in existing_reviews(tmp_path, SPECIMEN)] == [
        f"{SPECIMEN}.{SOURCE_HASH.split(':')[1][:12]}.review.json"
    ]
    assert len(existing_separation_reviews(tmp_path, SPECIMEN)) == 1


def test_requiring_acceptance_returns_the_review_for_these_exact_bytes(tmp_path: Path) -> None:
    review = build(manifest_bytes=b"the real manifest")
    write(tmp_path, review)
    found, path = require_separation_accepted(tmp_path, SPECIMEN, hash_bytes(b"the real manifest"))
    assert found == review
    assert path.name.endswith(".separation-review.json")


def test_requiring_acceptance_refuses_when_nobody_has_reviewed_anything(tmp_path: Path) -> None:
    with pytest.raises(ReviewError, match="Gate 3 is passed by a human hearing the stems"):
        require_separation_accepted(tmp_path, SPECIMEN, hash_bytes(b"anything"))


def test_requiring_acceptance_refuses_a_different_separation_and_names_both(
    tmp_path: Path,
) -> None:
    """The refusal this contract exists to make.

    A review is on disk, the specimen id matches, the directory matches — and
    the separation was regenerated, so the bytes are not the ones anyone heard.
    """
    write(tmp_path, build(manifest_bytes=b"the reviewed manifest"))
    with pytest.raises(ReviewError) as caught:
        require_separation_accepted(tmp_path, SPECIMEN, hash_bytes(b"a later manifest"))
    message = str(caught.value)
    assert hash_bytes(b"a later manifest") in message
    assert hash_bytes(b"the reviewed manifest") in message


def test_requiring_acceptance_refuses_stems_a_human_rejected(tmp_path: Path) -> None:
    review = build(manifest_bytes=b"m", accepted=False)
    write(tmp_path, review)
    with pytest.raises(ReviewError, match="did NOT accept"):
        require_separation_accepted(tmp_path, SPECIMEN, hash_bytes(b"m"))
