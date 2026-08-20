"""Recording that a human listened, and finding that record again.

A generated specimen is untracked bytes. The judgement about it is tracked, and
this module owns the small amount of machinery that keeps the two attached to
each other: where a review lives, how one is built from a generation manifest
plus a person's answers, and — the part every later stage depends on — how a
stage asks "were *these* bytes accepted" and gets an answer that cannot be
satisfied by a directory name.

That last point is the whole reason this module exists rather than being three
lines inside a command. `corpus/generated/sparse-funk-exposed-bass/source.wav`
is a path. `sparse-funk-exposed-bass` is a *specimen id*, which names an intent
and deliberately survives regeneration. Change the prompt, regenerate, and both
of those still resolve — to audio nobody has heard. Only the hash distinguishes
the rendering a person actually listened to from a later one that merely shares
its name, so :func:`require_accepted` compares hashes and reports both when they
disagree.

Reviews are stored one file per *rendering*, named for the specimen and the
first twelve hex digits of its hash, so two candidates for the same specimen are
two files rather than one file that quietly changed meaning.

Nothing here imports a model, reads audio, or needs the cabinet. It is stdlib
plus the contracts, so `separate` can check its precondition before it loads a
weight, and so the tests can exercise all of it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from spectral_loom.contracts import (
    CriterionResponse,
    GenerationManifest,
    HumanReview,
    ReviewCriterion,
    SpecimenReview,
)
from spectral_loom.hashing import hash_bytes

#: Tracked, unlike `corpus/generated/` and `corpus/derived/` beside it. A review
#: is history: it is the only thing that survives a clean clone to say a gate
#: was passed by ears.
REVIEWS_DIRNAME = "corpus/reviews"

#: How much of the hash goes in the filename. Twelve hex digits is enough to
#: keep two candidates apart on disk and short enough to read aloud; the file's
#: own contents carry the full hash and are what anything mechanical compares.
_HASH_PREFIX = 12


class ReviewError(Exception):
    """A review could not be written, read, or satisfied."""


# ---------------------------------------------------------------------------
# The gate 2 question set.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Criterion:
    """One question in a fixed question set.

    Fixed on purpose. The four below are `corpus/specs/example.yaml`'s own notes
    and `docs/roadmap.md`'s gate 2, and letting a reviewer invent the questions
    at the moment of answering them is how a gate stops meaning anything. A
    later gate with different questions adds its own set beside this one.
    """

    id: str
    flag: str
    question: str
    help: str


#: What gate 2 asks about a generated candidate. The wording is stored with each
#: answer in the written review, so changing this constant later cannot
#: retroactively change what an existing review claims.
GATE_2_CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        id="bass-audible-and-exposed",
        flag="--bass-exposed",
        question="Is the bass audible and exposed?",
        help="whether a bass line is audible and sits in front rather than buried",
    ),
    Criterion(
        id="useful-silence-between-phrases",
        flag="--silence-between-phrases",
        question="Is there useful silence between phrases?",
        help="whether the arrangement leaves space, so activity detection has something to find",
    ),
    Criterion(
        id="parts-separable-by-ear",
        flag="--parts-separable",
        question="Are the parts separable by ear?",
        help="whether a listener can follow the parts individually before any model tries to",
    ),
    Criterion(
        id="generator-failure-perceived",
        flag="--generator-failure",
        question=(
            "Was vocal bleed or another obvious generator failure perceived? In this context "
            "vocal bleed means unintended singing, humming, speech fragments, breathy vowel "
            "sounds, or voice-like pads despite the no-vocals request."
        ),
        help="whether anything sounded like a generator failure; 'yes' here argues for rejection",
    ),
)

#: What accepting a generated candidate at gate 2 commits the project to, stated
#: so that it cannot be quietly widened into a claim about the music. Written
#: into every gate 2 review.
GATE_2_PURPOSE = (
    "These exact bytes are suitable as this project's first experimental specimen. This is "
    "not a claim that any requested instrument, tempo, or key was objectively established: "
    "nothing has analysed the audio, and what it contains remains an open question for a "
    "song.timeline.json to answer."
)

#: How a gate 2 review is conducted, absent anything more specific from the
#: reviewer. Says what was *not* done as well as what was.
GATE_2_METHOD = (
    "Listened to the complete file. Unaided ears, no analysis, no separation, no measurement "
    "beyond the observed duration, sample rate, channel count and hash recorded here."
)


def criterion(identifier: str) -> Criterion:
    """Look up a gate 2 criterion, failing with the ids that do exist."""
    for item in GATE_2_CRITERIA:
        if item.id == identifier:
            return item
    raise ReviewError(
        f"no gate 2 criterion named {identifier!r}; the question set is "
        f"{', '.join(c.id for c in GATE_2_CRITERIA)}"
    )


# ---------------------------------------------------------------------------
# Hashing and paths.
# ---------------------------------------------------------------------------


def short_hash(content_hash: str) -> str:
    """The filename-sized form of a content hash, without its algorithm prefix."""
    return content_hash.split(":", 1)[-1][:_HASH_PREFIX]


def reviews_dir(repository_root: Path) -> Path:
    return repository_root / REVIEWS_DIRNAME


def review_path(repository_root: Path, specimen_id: str, source_hash: str) -> Path:
    """Where the review of one exact rendering lives.

    The hash is in the name rather than only in the contents so that a second
    candidate for the same specimen lands beside the first instead of on top of
    it. Two renderings are two judgements, even when one of them is a rejection.
    """
    return reviews_dir(repository_root) / (f"{specimen_id}.{short_hash(source_hash)}.review.json")


def existing_reviews(repository_root: Path, specimen_id: str) -> list[Path]:
    """Every review file on disk for one specimen id, in a stable order."""
    directory = reviews_dir(repository_root)
    if not directory.is_dir():
        return []
    return sorted(directory.glob(f"{specimen_id}.*.review.json"))


# ---------------------------------------------------------------------------
# Building and writing.
# ---------------------------------------------------------------------------


def build_review(
    manifest: GenerationManifest,
    *,
    manifest_bytes: bytes,
    cabinet_bytes: bytes,
    reviewer: str,
    reviewed_on: date,
    responses: dict[str, CriterionResponse],
    notes: dict[str, str] | None = None,
    accepted: bool,
    method: str = GATE_2_METHOD,
    purpose: str = GATE_2_PURPOSE,
    summary: str | None = None,
) -> SpecimenReview:
    """Bind a person's answers to the exact bytes a generation manifest describes.

    The observations are copied from the manifest rather than re-measured,
    because the manifest measured the same file and re-measuring here would
    invite the two to disagree. What is *not* copied is any restatement of the
    request: the prompt, the seed and the requested tempo travel only inside the
    provenance stage that is already labelled ``requested``.
    """
    missing = {c.id for c in GATE_2_CRITERIA} - set(responses)
    if missing:
        raise ReviewError(
            f"every gate 2 criterion needs an answer; missing "
            f"{', '.join(sorted(missing))}. A review with a question left blank is not a "
            f"review, it is a partially examined assumption."
        )

    given = notes or {}
    for identifier in given:
        criterion(identifier)  # raises with the known ids if this is a typo

    return SpecimenReview(
        specimen_id=manifest.specimen_id,
        spec_path=manifest.spec_path,
        spec_hash=manifest.spec_hash,
        source_audio=manifest.source_audio,
        generation_manifest_hash=hash_bytes(manifest_bytes),
        cabinet_hash=hash_bytes(cabinet_bytes),
        provenance=list(manifest.provenance),
        review=HumanReview(
            reviewer=reviewer,
            reviewed_on=reviewed_on,
            method=method,
            criteria=[
                ReviewCriterion(
                    id=item.id,
                    question=item.question,
                    response=responses[item.id],
                    notes=given.get(item.id),
                )
                for item in GATE_2_CRITERIA
            ],
            accepted=accepted,
            purpose=purpose,
            notes=summary,
        ),
    )


def write_review(path: Path, review: SpecimenReview) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(review.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_review(path: Path) -> SpecimenReview:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"cannot read {path}: {exc}") from exc
    try:
        return SpecimenReview.model_validate(document)
    except ValidationError as exc:
        raise ReviewError(f"{path} is not a valid specimen review: {exc}") from exc


# ---------------------------------------------------------------------------
# The precondition every later stage asks about.
# ---------------------------------------------------------------------------


def require_accepted(
    repository_root: Path, specimen_id: str, source_hash: str
) -> tuple[SpecimenReview, Path]:
    """The accepted review for exactly these bytes, or a refusal that says why.

    Four different failures, kept apart because they call for four different
    actions: nobody has reviewed this specimen at all, somebody reviewed a
    *different* rendering of it, somebody reviewed these bytes and rejected
    them, or the review file itself is unreadable. Collapsing them into "not
    accepted" would leave a person guessing which one they are in.
    """
    candidates = existing_reviews(repository_root, specimen_id)
    if not candidates:
        raise ReviewError(
            f"no review exists for specimen {specimen_id!r} under "
            f"{reviews_dir(repository_root)}. Gate 2 is passed by a human listening, not by a "
            f"file existing: listen to the audio, then record the verdict with "
            f"`spectral-loom accept {specimen_id} ...`."
        )

    reviews = [(path, load_review(path)) for path in candidates]

    for path, review in reviews:
        if review.source_audio.hash != source_hash:
            continue
        if not review.review.accepted:
            raise ReviewError(
                f"{path} records that {review.review.reviewer} reviewed exactly these bytes on "
                f"{review.review.reviewed_on} and did NOT accept them. Nothing downstream runs "
                f"on a rejected specimen."
            )
        return review, path

    reviewed = ", ".join(f"{r.source_audio.hash} ({p.name})" for p, r in reviews)
    raise ReviewError(
        f"the audio on disk for specimen {specimen_id!r} hashes to {source_hash}, which nobody "
        f"has reviewed. Reviews exist for {reviewed}. A specimen id names an intent and "
        f"survives regeneration, so a matching directory name is not evidence that these "
        f"bytes are the ones a person listened to — and this stage will not treat it as such."
    )
