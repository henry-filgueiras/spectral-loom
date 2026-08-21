"""Recording that a human listened, and finding that record again.

A generated specimen is untracked bytes. The judgement about it is tracked, and
this module owns the small amount of machinery that keeps the two attached to
each other: where a review lives, how one is built from a generation manifest
plus a person's answers, and — the part every later stage depends on — how a
stage asks "were *these* bytes accepted" and gets an answer that cannot be
satisfied by a directory name.

Two kinds of review live here, because they are the same problem twice. A
:class:`~spectral_loom.contracts.SpecimenReview` is keyed by the audio's hash; a
:class:`~spectral_loom.contracts.SeparationReview` is keyed by the separation
manifest's hash. They share the human-review primitive the contracts already
define and nothing else, which is as much generalization as two cases earn.

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
    ReviewedArtifact,
    SeparationManifest,
    SeparationReview,
    SongTimeline,
    SpecimenReview,
    SupplementaryListening,
    TimelineReview,
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


def criterion(identifier: str, criteria: tuple[Criterion, ...] = GATE_2_CRITERIA) -> Criterion:
    """Look up a criterion in a question set, failing with the ids that do exist."""
    for item in criteria:
        if item.id == identifier:
            return item
    raise ReviewError(
        f"no criterion named {identifier!r} in this question set; it is "
        f"{', '.join(c.id for c in criteria)}"
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


# ---------------------------------------------------------------------------
# The gate 3 question set: what a human decided about one exact separation.
# ---------------------------------------------------------------------------

#: What gate 3 asks about a separation, per model output and then as a whole.
#:
#: Every wording here is load-bearing, because the easiest way to ruin this gate
#: is to ask a question whose answer is a claim about the recording. "Was there
#: enough clearly audible cymbal material to judge cymbal separation" can be
#: answered honestly; "did the separator lose the cymbals" cannot, if nobody can
#: say what was there to lose. Likewise `vocals` is asked about what was
#: *perceived in the model output*, never about what the source contained.
#:
#: As with gate 2, each answer is written down with the question's exact wording,
#: so editing this constant later cannot retroactively change what an existing
#: review claims.
GATE_3_CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        id="bass-clearly-isolated",
        flag="--bass-isolated",
        question="Is the bass line clearly isolated in the `bass` output?",
        help="whether a bass line can be followed on its own in that output",
    ),
    Criterion(
        id="bass-leakage-perceived",
        flag="--bass-leakage",
        question="Was leakage from another part perceived in the `bass` output?",
        help="whether anything that does not belong to a bass line was heard in it",
    ),
    Criterion(
        id="bass-material-missing-or-smeared",
        flag="--bass-damaged",
        question=(
            "Did bass material perceptibly disappear, or were its attacks smeared, in the "
            "`bass` output?"
        ),
        help="whether the separation dropped or blurred material the reviewer expected to hear",
    ),
    Criterion(
        id="drums-kick-snare-hat-coherent",
        flag="--drums-coherent",
        question="Is the kick, snare/rimshot and hi-hat material coherent in the `drums` output?",
        help="whether those elements are intact and followable in that output",
    ),
    Criterion(
        id="drums-cymbal-material-sufficient-to-judge",
        flag="--drums-cymbal-judgeable",
        question=(
            "Was there enough clearly audible cymbal or crash material in the accepted source "
            "to judge cymbal separation at all?"
        ),
        help=(
            "whether the source offered material from which a cymbal verdict could be drawn; "
            "'no' records that the question is unanswerable here, not that the model failed"
        ),
    ),
    Criterion(
        id="drums-melodic-leakage-or-damaged-transients",
        flag="--drums-damaged",
        question=("Was melodic leakage or transient damage perceived in the `drums` output?"),
        help="whether pitched material leaked in, or attacks were damaged",
    ),
    Criterion(
        id="other-single-instrument",
        flag="--other-single-instrument",
        question="Does the `other` output present as a single instrument?",
        help=(
            "whether that output is one voice or several lumped together; 'no' is the answer "
            "that forbids renaming it after an instrument"
        ),
    ),
    Criterion(
        id="other-bass-or-drums-misassigned",
        flag="--other-misassigned",
        question="Is substantial bass or drum content assigned to the `other` output?",
        help="whether the separator put material there that its own bass and drums outputs claim",
    ),
    Criterion(
        id="vocals-meaningful-content-perceived",
        flag="--vocals-content",
        question=(
            "Was any perceptually meaningful content — voice-like or instrumental — heard in "
            "the `vocals` output?"
        ),
        help=(
            "what was perceived in that model output; 'no' is a failure to assign and is never "
            "evidence that the source contained no singing"
        ),
    ),
    Criterion(
        id="whole-character-retained",
        flag="--character-retained",
        question="Does the reconstructed mix retain the source's overall musical character?",
        help="whether the sum of the outputs still sounds like the piece",
    ),
    Criterion(
        id="whole-objectionable-artifacts",
        flag="--artifacts-objectionable",
        question=(
            "Was obvious phase destruction, pumping, or missing musical material perceived in "
            "the reconstruction?"
        ),
        help="whether the reconstruction has audible damage; 'yes' here argues for rejection",
    ),
    Criterion(
        id="whole-level-difference-perceived",
        flag="--level-difference",
        question="Was the reconstruction perceived as differing in overall level from the source?",
        help=(
            "a perceptual observation about loudness, kept as one rather than replaced by a "
            "signal metric that answers a different question"
        ),
    ),
    Criterion(
        id="fit-as-evidence-for-activity-and-onset-inference",
        flag="--fit-as-evidence",
        question=(
            "Are these outputs good enough to serve as evidence inputs for experimental "
            "activity and onset inference?"
        ),
        help="the decisive question; 'no' means nothing downstream reads these files",
    ),
)

#: What accepting a separation at gate 3 commits the project to. Narrow on
#: purpose, and narrower than it looks: it licenses reading these files, and
#: licenses nothing about what is in them.
GATE_3_PURPOSE = (
    "These exact separated bytes are fit to serve as evidence inputs for experimental activity "
    "and onset inference. This is not a claim that any output is a verified instrument, and it "
    "is not a claim that anything absent from an output is absent from the recording: an output "
    "in which nothing was perceived is a failure to assign, never proof that nobody played."
)

#: How a gate 3 review is conducted, absent anything more specific.
GATE_3_METHOD = (
    "Auditioned every model output and the engineering diagnostics in the Stem Observatory, on "
    "one shared transport clock, with solo, mute, loop and A/B against the source mix. Unaided "
    "ears. No measurement beyond the hashes, durations, rates, channel counts, peaks and "
    "residual levels the separation manifest already recorded."
)


def separation_review_path(
    repository_root: Path, specimen_id: str, separation_manifest_hash: str
) -> Path:
    """Where the review of one exact separation lives.

    Keyed by the *separation manifest's* hash rather than by the source hash,
    because one accepted recording can be separated many times — another
    revision, another backend, another parameter — and each of those is a
    different set of bytes to have an opinion about.

    The suffix differs from a specimen review's by more than a word: it has to,
    because ``existing_reviews`` globs for ``*.review.json`` and a filename that
    matched both would make one kind of review readable as the other.
    """
    return reviews_dir(repository_root) / (
        f"{specimen_id}.{short_hash(separation_manifest_hash)}.separation-review.json"
    )


def existing_separation_reviews(repository_root: Path, specimen_id: str) -> list[Path]:
    """Every separation review on disk for one specimen id, in a stable order."""
    directory = reviews_dir(repository_root)
    if not directory.is_dir():
        return []
    return sorted(directory.glob(f"{specimen_id}.*.separation-review.json"))


def reviewed_artifacts(manifest: SeparationManifest) -> list[ReviewedArtifact]:
    """Every file the Stem Observatory puts in front of a reviewer, by hash.

    The source first because it is the evidence, the model outputs in the
    separator's own order, then the rendered diagnostics. A diagnostic without
    audio is a measurement rather than an exhibit and is not listed: nobody
    listened to a number.
    """
    artifacts = [
        ReviewedArtifact(
            name="source",
            kind="source",
            path=manifest.source_path,
            hash=manifest.source_audio.hash,
        )
    ]
    artifacts += [
        ReviewedArtifact(
            name=stem.model_output,
            kind="model_output",
            path=stem.audio.path,
            hash=stem.audio.hash,
        )
        for stem in manifest.stems
    ]
    artifacts += [
        ReviewedArtifact(
            name=diagnostic.id,
            kind="diagnostic",
            path=diagnostic.audio.path,
            hash=diagnostic.audio.hash,
        )
        for diagnostic in manifest.diagnostics
        if diagnostic.audio is not None
    ]
    return artifacts


def build_separation_review(
    manifest: SeparationManifest,
    *,
    manifest_path: str,
    manifest_bytes: bytes,
    reviewer: str,
    reviewed_on: date,
    responses: dict[str, CriterionResponse],
    notes: dict[str, str] | None = None,
    accepted: bool,
    method: str = GATE_3_METHOD,
    purpose: str = GATE_3_PURPOSE,
    summary: str | None = None,
    supplementary: list[SupplementaryListening] | None = None,
) -> SeparationReview:
    """Bind a person's answers to the exact separation a manifest describes.

    The observations are copied from the manifest rather than re-measured, for
    the same reason :func:`build_review` copies them: the manifest measured
    these files, and a second measurement here would only create an opportunity
    for the two to disagree.
    """
    missing = {c.id for c in GATE_3_CRITERIA} - set(responses)
    if missing:
        raise ReviewError(
            f"every gate 3 criterion needs an answer; missing "
            f"{', '.join(sorted(missing))}. A review with a question left blank is not a "
            f"review, it is a partially examined assumption."
        )

    given = notes or {}
    for identifier in given:
        criterion(identifier, GATE_3_CRITERIA)  # raises with the known ids if this is a typo

    return SeparationReview(
        specimen_id=manifest.specimen_id,
        source_audio=manifest.source_audio,
        specimen_review_hash=manifest.review_hash,
        separation_manifest_path=manifest_path,
        separation_manifest_hash=hash_bytes(manifest_bytes),
        separation_cache_key=manifest.cache_key,
        separator=manifest.separator,
        reviewed_artifacts=reviewed_artifacts(manifest),
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
                for item in GATE_3_CRITERIA
            ],
            accepted=accepted,
            purpose=purpose,
            notes=summary,
        ),
        supplementary=list(supplementary or []),
    )


def write_separation_review(path: Path, review: SeparationReview) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(review.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_separation_review(path: Path) -> SeparationReview:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"cannot read {path}: {exc}") from exc
    try:
        return SeparationReview.model_validate(document)
    except ValidationError as exc:
        raise ReviewError(f"{path} is not a valid separation review: {exc}") from exc


def require_separation_accepted(
    repository_root: Path, specimen_id: str, separation_manifest_hash: str
) -> tuple[SeparationReview, Path]:
    """The accepted review for exactly this separation, or a refusal that says why.

    The same four failures :func:`require_accepted` keeps apart, one layer down,
    and kept apart for the same reason: "not accepted" is four different
    situations calling for four different actions.
    """
    candidates = existing_separation_reviews(repository_root, specimen_id)
    if not candidates:
        raise ReviewError(
            f"no separation review exists for specimen {specimen_id!r} under "
            f"{reviews_dir(repository_root)}. Gate 3 is passed by a human hearing the stems, "
            f"not by them existing: audition them with "
            f"`spectral-loom review-separation {specimen_id}`, then record the verdict with "
            f"`spectral-loom accept-separation {specimen_id} ...`."
        )

    reviews = [(path, load_separation_review(path)) for path in candidates]

    for path, review in reviews:
        if review.separation_manifest_hash != separation_manifest_hash:
            continue
        if not review.review.accepted:
            raise ReviewError(
                f"{path} records that {review.review.reviewer} auditioned exactly this "
                f"separation on {review.review.reviewed_on} and did NOT accept it. Nothing "
                f"downstream reads stems a human rejected."
            )
        return review, path

    reviewed = ", ".join(f"{r.separation_manifest_hash} ({p.name})" for p, r in reviews)
    raise ReviewError(
        f"the separation manifest on disk for specimen {specimen_id!r} hashes to "
        f"{separation_manifest_hash}, which nobody has reviewed. Reviews exist for {reviewed}. "
        f"A separation lives in a directory the next run reuses, so a result being present "
        f"where an accepted one used to be is not evidence that anybody heard it — and this "
        f"stage will not treat it as such."
    )


# ---------------------------------------------------------------------------
# The gate 4 question set: what a human decided about one compiled timeline.
# ---------------------------------------------------------------------------

#: What gate 4 asks. The wordings carry the same load they did at gate 3: every
#: answer is a perception of a *detector's output*, and none of them may be read
#: as a measurement of the recording. "Audible events were found that the
#: detector declined" says a person heard something the rule did not accept; it
#: establishes nothing about how many events the music holds.
#:
#: The last two are the ones that actually decide the gate, and they are
#: judgements rather than observations. They are asked last on purpose.
GATE_4_CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        id="onsets-coincide-with-audible-events",
        flag="--onsets-coincide",
        question="Do accepted onsets generally coincide with events audible in the model output?",
        help="whether the claims the detector made land on things a listener can hear",
    ),
    Criterion(
        id="audible-events-the-detector-declined",
        flag="--onsets-missed",
        question="Were audible events found that the detector declined?",
        help="whether the review turned up real material the rule turned down",
    ),
    Criterion(
        id="intervals-match-perceived-structure",
        flag="--intervals-match",
        question=(
            "Do activity intervals begin and end where musical structure perceptually begins "
            "and ends?"
        ),
        help="whether the spans correspond to anything a listener would call a unit",
    ),
    Criterion(
        id="near-silent-output-correctly-unclaimed",
        flag="--near-silent-unclaimed",
        question=(
            "Was the near-silent model output correctly left unclaimed, and did anything it "
            "would claim under relaxed parameters sound like nothing?"
        ),
        help="whether the absolute floor is doing the job it was chosen for",
    ),
    Criterion(
        id="cross-stem-leakage-perceived",
        flag="--leakage",
        question=(
            "Was content belonging to one model output perceived in another output's events?"
        ),
        help=(
            "whether any event is a correct reading of an incorrect stem; this is about the "
            "separation showing through, not about the detector"
        ),
    ),
    Criterion(
        id="event-timings-perceptually-aligned",
        flag="--timings-aligned",
        question="Are event timings perceptually aligned with the recording?",
        help="whether a marker lands where the sound is, within the detector's own resolution",
    ),
    Criterion(
        id="mistakes-nameable-in-the-instrument",
        flag="--mistakes-nameable",
        question=(
            "Were the detector's mistakes findable and nameable using the review surface, "
            "without reading JSON?"
        ),
        help=(
            "the gate's real subject: an inference nobody can inspect is not evidence of "
            "anything, however accurate it happens to be"
        ),
    ),
    Criterion(
        id="vocabulary-useful-for-synchronized-visuals",
        flag="--vocabulary-useful",
        question=(
            "Does this minimal vocabulary already feel useful for future synchronized visual work?"
        ),
        help="a judgement about where this is going, not an observation about what it does",
    ),
    Criterion(
        id="semantics-misleading-enough-to-fail",
        flag="--misleading",
        question=(
            "Is any event semantics misleading enough that this gate should fail and the rule "
            "be reconsidered?"
        ),
        help="the decisive question; 'yes' fails the gate",
    ),
)

#: What accepting a timeline at gate 4 commits the project to. Narrower than it
#: looks, and deliberately so.
GATE_4_PURPOSE = (
    "This exact compiled timeline is a usable, attributable semantic artifact for the next stage "
    "of this project, and its mistakes are findable by a person. This is NOT a claim that its "
    "events are musically correct: a timeline may pass this gate while missing real events and "
    "claiming unreal ones, provided the misses and the claims have been found and written down. "
    "Accepting it licenses reading the document; it licenses nothing about what the recording "
    "contains."
)

GATE_4_METHOD = (
    "Spot-checked every model output in the Timeline Observatory against the audio, on one shared "
    "transport clock, with a click track sonifying the markers, hypothetical floor and multiplier "
    "controls for asking what another rule would have accepted, and the declined peaks drawn "
    "alongside the accepted ones. Unaided ears. No measurement by the reviewer beyond what the "
    "instrument displayed."
)


def timeline_review_path(repository_root: Path, specimen_id: str, timeline_hash: str) -> Path:
    """Where the review of one exact compiled timeline lives."""
    return reviews_dir(repository_root) / (
        f"{specimen_id}.{short_hash(timeline_hash)}.timeline-review.json"
    )


def existing_timeline_reviews(repository_root: Path, specimen_id: str) -> list[Path]:
    directory = reviews_dir(repository_root)
    if not directory.is_dir():
        return []
    return sorted(directory.glob(f"{specimen_id}.*.timeline-review.json"))


def write_timeline_review(path: Path, review: TimelineReview) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(review.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_timeline_review(path: Path) -> TimelineReview:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"cannot read {path}: {exc}") from exc
    try:
        return TimelineReview.model_validate(document)
    except ValidationError as exc:
        raise ReviewError(f"{path} is not a valid timeline review: {exc}") from exc


def require_timeline_accepted(
    repository_root: Path, specimen_id: str, timeline_hash: str
) -> tuple[TimelineReview, Path]:
    """The accepted review for exactly this timeline, or a refusal that says why.

    Nothing consumes this yet. It exists because gate 5 and gate 6 will read a
    timeline, and the argument that made `separate` require gate 2 and `compile`
    require gate 3 does not weaken by being made a third time.
    """
    candidates = existing_timeline_reviews(repository_root, specimen_id)
    if not candidates:
        raise ReviewError(
            f"no timeline review exists for specimen {specimen_id!r} under "
            f"{reviews_dir(repository_root)}. Gate 4 is passed by a human checking events "
            f"against audio: open the Timeline Observatory with "
            f"`spectral-loom review-timeline {specimen_id}`, then record the verdict with "
            f"`spectral-loom accept-timeline {specimen_id} ...`."
        )
    reviews = [(path, load_timeline_review(path)) for path in candidates]
    for path, review in reviews:
        if review.timeline_hash != timeline_hash:
            continue
        if not review.review.accepted:
            raise ReviewError(
                f"{path} records that {review.review.reviewer} spot-checked exactly this "
                f"timeline on {review.review.reviewed_on} and did NOT accept it."
            )
        return review, path
    reviewed = ", ".join(f"{r.timeline_hash} ({p.name})" for p, r in reviews)
    raise ReviewError(
        f"the timeline on disk for specimen {specimen_id!r} hashes to {timeline_hash}, which "
        f"nobody has reviewed. Reviews exist for {reviewed}. A recompilation under a changed "
        f"parameter is a different document and does not inherit a verdict."
    )


def build_timeline_review(
    timeline: SongTimeline,
    *,
    timeline_path: str,
    timeline_hash: str,
    cache_key: str,
    specimen_review_hash: str,
    separation_review_hash: str,
    event_counts: dict[str, dict[str, int]],
    analysis_stages: list[str],
    reviewer: str,
    reviewed_on: date,
    responses: dict[str, CriterionResponse],
    notes: dict[str, str] | None = None,
    accepted: bool,
    method: str = GATE_4_METHOD,
    purpose: str = GATE_4_PURPOSE,
    summary: str | None = None,
    findings: str | None = None,
) -> TimelineReview:
    """Bind a person's answers to the exact document they checked."""
    missing = {c.id for c in GATE_4_CRITERIA} - set(responses)
    if missing:
        raise ReviewError(
            f"every gate 4 criterion needs an answer; missing "
            f"{', '.join(sorted(missing))}. A review with a question left blank is not a "
            f"review, it is a partially examined assumption."
        )
    given = notes or {}
    for identifier in given:
        criterion(identifier, GATE_4_CRITERIA)

    return TimelineReview(
        specimen_id=timeline.specimen_id,
        timeline_path=timeline_path,
        timeline_hash=timeline_hash,
        source_audio=timeline.source_audio,
        separation_review_hash=separation_review_hash,
        specimen_review_hash=specimen_review_hash,
        cache_key=cache_key,
        analysis=[p for p in timeline.provenance if p.stage in analysis_stages],
        event_counts=event_counts,
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
                for item in GATE_4_CRITERIA
            ],
            accepted=accepted,
            purpose=purpose,
            notes=summary,
        ),
        findings=findings,
    )
