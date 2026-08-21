"""Tests for the tracked record that a human listened.

Two things are being defended here and they pull in opposite directions.

The first is the truth-layer rule. A review is the most tempting place in the
project to write down "this song has an exposed bass at 96 BPM", because a
person just finished listening and that is what it felt like they established.
They did not. They established that they *perceived* something, and the document
has to keep saying so — including after the prompt's words have been copied into
it as part of the generation provenance.

The second is the hash binding. A specimen id names an intent and survives
regeneration, so `sparse-funk-exposed-bass` will still resolve after somebody
changes the prompt and generates again. Everything downstream asks "were these
bytes accepted", and the answer must not be satisfiable by a matching directory
name. Most of the tests below are about that question being asked properly.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from spectral_loom.contracts import (
    CriterionResponse,
    GenerationManifest,
    Provenance,
    SourceAudio,
    SpecimenReview,
    TruthLayer,
)
from spectral_loom.review import (
    GATE_2_CRITERIA,
    ReviewError,
    build_review,
    existing_reviews,
    load_review,
    require_accepted,
    review_path,
    short_hash,
    write_review,
)

SOURCE_HASH = "sha256:" + "a" * 64
OTHER_HASH = "sha256:" + "b" * 64
SPEC_HASH = "sha256:" + "c" * 64

#: Requested musical values, so that a test can assert none of them leaks out of
#: the one place they are allowed to live. The specimen *id* is deliberately not
#: on this list: `sparse-funk-exposed-bass` echoes the request because it names
#: the intent, and it is an identifier rather than a claim about the audio.
REQUESTED_WORDS = ("96", "D minor", "electric bass", "close-miked")


def manifest(source_hash: str = SOURCE_HASH) -> GenerationManifest:
    """A generation manifest shaped like the real one, with a request in it."""
    return GenerationManifest(
        specimen_id="sparse-funk-exposed-bass",
        spec_path="corpus/specs/example.yaml",
        spec_hash=SPEC_HASH,
        source_audio=SourceAudio(
            hash=source_hash, duration_s=45.0, sample_rate_hz=48000, channels=2
        ),
        provenance=[
            Provenance(
                stage="generate",
                tool="diffusers.AceStepPipeline",
                tool_revision="diffusers==0.40.0 ACE-Step/x@" + "0" * 40,
                truth_layer=TruthLayer.REQUESTED,
                input_hashes={"spec": SPEC_HASH},
                parameters={
                    "prompt": "Sparse instrumental funk, exposed electric bass, close-miked",
                    "requested_bpm": 96,
                    "requested_keyscale": "D minor",
                    "seed": 20260820,
                },
                output_hashes={"source": source_hash},
                runtime="cpython3.11 darwin-arm64 mps",
                # A real generation stage answers all seven questions in
                # `docs/provenance.md`, and a fixture that answered fewer would
                # let a test pass against data the pipeline never produces.
                started_at=datetime(2026, 8, 20, 22, 28, 31, tzinfo=UTC),
                duration_ms=15651,
            )
        ],
    )


ALL_YES = {c.id: CriterionResponse.YES for c in GATE_2_CRITERIA}


def review(
    *, accepted: bool = True, source_hash: str = SOURCE_HASH, **kwargs: object
) -> SpecimenReview:
    return build_review(
        manifest(source_hash),
        manifest_bytes=b"{}",
        cabinet_bytes=b"schema_version = '1'",
        reviewer="Henry",
        reviewed_on=date(2026, 8, 20),
        responses=dict(ALL_YES),
        accepted=accepted,
        **kwargs,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# What a review is allowed to say.
# ---------------------------------------------------------------------------


def test_a_review_copies_observations_rather_than_re_measuring_them() -> None:
    """The manifest measured the file; disagreeing with it would be a bug."""
    written = review()
    assert written.source_audio == manifest().source_audio
    assert written.spec_hash == SPEC_HASH


def test_the_request_survives_only_inside_the_stage_labelled_requested() -> None:
    """The point of the whole document, asserted rather than trusted.

    Serialize the review with its generation provenance removed — the one place
    a prompt is allowed to be, because that stage is labelled `requested` — and
    nothing the prompt asked for may appear in what is left.
    """
    document = review().model_dump(mode="json")
    document["provenance"] = []
    remaining = json.dumps(document)

    for word in REQUESTED_WORDS:
        assert word not in remaining, (
            f"{word!r} leaked out of the requested layer and into a document that a reader "
            f"could mistake for an observation about the audio"
        )


def test_the_purpose_of_an_acceptance_is_stated_and_narrow() -> None:
    stated = review().review.purpose
    assert "experimental specimen" in stated
    assert "not a claim" in stated


def test_a_rejection_is_representable_and_carries_what_was_wrong() -> None:
    """A record that can only say yes is a marketing document."""
    rejected = review(
        accepted=False, summary="Vocal-like pad from 0:12; the bass is buried under it."
    )
    assert rejected.review.accepted is False
    assert rejected.review.notes is not None
    assert "buried" in rejected.review.notes


def test_every_criterion_must_be_answered() -> None:
    partial = {c.id: CriterionResponse.YES for c in GATE_2_CRITERIA[:2]}
    with pytest.raises(ReviewError, match="missing"):
        build_review(
            manifest(),
            manifest_bytes=b"{}",
            cabinet_bytes=b"",
            reviewer="Henry",
            reviewed_on=date(2026, 8, 20),
            responses=partial,
            accepted=True,
        )


def test_a_note_for_an_unknown_criterion_is_a_typo_not_a_new_question() -> None:
    with pytest.raises(ReviewError, match="no criterion named"):
        review(notes={"bass-is-nice": "it is"})


def test_unclear_is_available_so_a_reviewer_need_not_say_no() -> None:
    """Failing to perceive something is not establishing its absence."""
    hedged = build_review(
        manifest(),
        manifest_bytes=b"{}",
        cabinet_bytes=b"",
        reviewer="Henry",
        reviewed_on=date(2026, 8, 20),
        responses={**ALL_YES, "parts-separable-by-ear": CriterionResponse.UNCLEAR},
        accepted=True,
    )
    answers = {c.id: c.response for c in hedged.review.criteria}
    assert answers["parts-separable-by-ear"] is CriterionResponse.UNCLEAR


def test_a_review_must_be_about_bytes_its_own_provenance_produced() -> None:
    """A judgement attached to audio the record cannot attribute is worthless."""
    document = review().model_dump(mode="json")
    document["source_audio"]["hash"] = OTHER_HASH
    with pytest.raises(ValidationError, match="not among the artifacts"):
        SpecimenReview.model_validate(document)


def test_duplicate_criterion_ids_are_rejected() -> None:
    document = review().model_dump(mode="json")
    document["review"]["criteria"].append(document["review"]["criteria"][0])
    with pytest.raises(ValidationError, match="duplicate review criterion"):
        SpecimenReview.model_validate(document)


# ---------------------------------------------------------------------------
# Where a review lives, and finding it again.
# ---------------------------------------------------------------------------


def test_a_review_is_named_for_the_rendering_not_only_the_specimen(tmp_path: Path) -> None:
    """Two candidates for one specimen are two files, not one that changed."""
    first = review_path(tmp_path, "sparse-funk-exposed-bass", SOURCE_HASH)
    second = review_path(tmp_path, "sparse-funk-exposed-bass", OTHER_HASH)
    assert first != second
    assert short_hash(SOURCE_HASH) in first.name
    assert first.parent == second.parent


def test_a_written_review_round_trips(tmp_path: Path) -> None:
    target = review_path(tmp_path, "sparse-funk-exposed-bass", SOURCE_HASH)
    write_review(target, review())
    assert load_review(target) == review()
    assert existing_reviews(tmp_path, "sparse-funk-exposed-bass") == [target]


def test_require_accepted_returns_the_review_for_exactly_these_bytes(tmp_path: Path) -> None:
    write_review(review_path(tmp_path, "sparse-funk-exposed-bass", SOURCE_HASH), review())
    found, path = require_accepted(tmp_path, "sparse-funk-exposed-bass", SOURCE_HASH)
    assert found.review.accepted
    assert path.exists()


def test_require_accepted_refuses_when_nobody_has_reviewed_the_specimen(tmp_path: Path) -> None:
    with pytest.raises(ReviewError, match="Gate 2 is passed by a human listening"):
        require_accepted(tmp_path, "sparse-funk-exposed-bass", SOURCE_HASH)


def test_require_accepted_refuses_a_different_rendering_of_the_same_specimen(
    tmp_path: Path,
) -> None:
    """The test this whole module exists for.

    A review of *some* rendering of `sparse-funk-exposed-bass` is on disk, and
    the audio on disk is different audio. A matching directory name must not be
    mistaken for a human having listened.
    """
    write_review(review_path(tmp_path, "sparse-funk-exposed-bass", SOURCE_HASH), review())

    with pytest.raises(ReviewError) as caught:
        require_accepted(tmp_path, "sparse-funk-exposed-bass", OTHER_HASH)

    message = str(caught.value)
    assert OTHER_HASH in message, "the refusal must name the hash that was found"
    assert SOURCE_HASH in message, "the refusal must name the hash that was reviewed"
    assert "survives regeneration" in message


def test_require_accepted_refuses_bytes_a_human_rejected(tmp_path: Path) -> None:
    write_review(
        review_path(tmp_path, "sparse-funk-exposed-bass", SOURCE_HASH),
        review(accepted=False, summary="vocal-like pad"),
    )
    with pytest.raises(ReviewError, match="did NOT accept"):
        require_accepted(tmp_path, "sparse-funk-exposed-bass", SOURCE_HASH)


def test_an_unreadable_review_is_a_refusal_rather_than_a_miss(tmp_path: Path) -> None:
    target = review_path(tmp_path, "sparse-funk-exposed-bass", SOURCE_HASH)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{not json", encoding="utf-8")
    with pytest.raises(ReviewError, match="cannot read"):
        require_accepted(tmp_path, "sparse-funk-exposed-bass", SOURCE_HASH)


# ---------------------------------------------------------------------------
# The committed review of the actual specimen.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_the_committed_gate_2_review_is_valid_and_says_what_it_should() -> None:
    """A tracked document nothing else in the suite would notice breaking.

    The audio it describes is untracked and is not on a CI runner, so this
    checks the document rather than the bytes: it validates, it accepts, and it
    answers every question gate 2 asks.
    """
    found = existing_reviews(REPO_ROOT, "sparse-funk-exposed-bass")
    assert found, "gate 2's acceptance must survive a clean clone"

    accepted = [load_review(path) for path in found]
    passing = [r for r in accepted if r.review.accepted]
    assert len(passing) == 1, "exactly one rendering of this specimen has been accepted"

    only = passing[0]
    assert only.review.reviewer == "Henry"
    assert {c.id for c in only.review.criteria} == {c.id for c in GATE_2_CRITERIA}
    assert only.source_audio.duration_s == 45.0
    assert only.source_audio.sample_rate_hz == 48000
    assert only.source_audio.channels == 2
