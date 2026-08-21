"""Compile one accepted separation into a ``song.timeline.json``.

The third pipeline stage, and the first that produces the artifact the whole
project is named for. ``docs/architecture.md`` calls the timeline the
language-neutral compiler boundary: everything downstream reads this file, and
nothing downstream may write to it.

**What it will not run on.** Two human verdicts, both mechanical, both checked
before a sample is read. Gate 2 accepted the source *bytes*; gate 3 accepted the
*separation*, identified by its manifest's own content hash. Then every stem is
re-hashed against both the manifest and the review, because a specimen id names
an intent and a separation directory is reused by the next run — a compile that
gated on a path would be one re-separation away from inheriting a verdict about
different audio.

**What the events are.** Exactly three types, because gate 4 admits three:
``activity.sample`` (observed), ``activity.interval`` and ``onset`` (inferred).
:mod:`spectral_loom.analysis` holds the arithmetic and the argument for every
parameter in it. Nothing here adds a note, a beat, a tempo, a section, a chord,
or an instrument.

**Where the human verdicts are not.** They are preconditions and they are in the
build receipt; they are *not* provenance stages in the timeline.
``decision:10`` settled that a person's judgement about fitness is not one of the
four truth layers and not a stage — it emits no artifact and cannot be
recomputed — and that reasoning does not change because the document changed.
What the timeline carries instead is the lineage of the *arithmetic*: the
generation stage and the separation stage copied verbatim, then the three
analysis stages, so the stems do not appear from nowhere.

**Determinism is a requirement, not a hope.** Recompiling unchanged inputs must
produce byte-identical bytes, because a boundary artifact that changes when
nothing changed cannot be diffed, cached, or compared against a later run. So
the canonical document contains no wall-clock, no elapsed time, no path outside
the repository, no random identifier, and no ordering that depends on how a
dictionary happened to iterate. Everything that *is* run telemetry — when this
ran, how long it took — lives in a receipt beside the timeline, which is where
it can be useful without being load-bearing.

The receipt is deliberately not one of the published contracts. `schemas/` is
the language-neutral surface another implementation reads; a local build record
that only this module writes and only this module reads has no business in it.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
from pydantic import BaseModel, ConfigDict, ValidationError

from spectral_loom import __version__
from spectral_loom.analysis import (
    ACTIVITY_ENTER_DBFS,
    ACTIVITY_EXIT_DBFS,
    ACTIVITY_HOP_SAMPLES,
    ACTIVITY_MERGE_GAP_S,
    ACTIVITY_MIN_DURATION_S,
    ACTIVITY_WINDOW_SAMPLES,
    AMPLITUDE_PLACES,
    DB_PLACES,
    FLUX_PLACES,
    ONSET_FFT_SAMPLES,
    ONSET_FLUX_FLOOR,
    ONSET_HOP_SAMPLES,
    ONSET_MEDIAN_MULTIPLIER,
    ONSET_MEDIAN_RADIUS_FRAMES,
    ONSET_MIN_GAP_S,
    ONSET_PEAK_RADIUS_FRAMES,
    SILENCE_FLOOR_DBFS,
    TIME_PLACES,
    AnalysisError,
    infer_intervals,
    infer_onsets,
    measure_activity,
    quantize,
    read_wav_mono,
)
from spectral_loom.contracts import (
    TIMELINE_SCHEMA_ID,
    TIMELINE_SCHEMA_VERSION,
    Event,
    Evidence,
    Extension,
    Provenance,
    SeparationManifest,
    SeparationReview,
    SongTimeline,
    SpecimenReview,
    Track,
    TruthLayer,
)
from spectral_loom.hashing import hash_bytes, hash_file
from spectral_loom.review import ReviewError, require_accepted, require_separation_accepted
from spectral_loom.separate import (
    DERIVED_DIRNAME,
    SEPARATION_DIRNAME,
    SEPARATION_MANIFEST_FILENAME,
    SeparationError,
    compute_cache_key,
)
from spectral_loom.separate import load_manifest as load_separation_manifest

#: Where a compiled timeline and its build receipt land, beside the separation
#: they were compiled from. Ignored by Git twice over: `corpus/derived/` is
#: ignored, and so is `*.timeline.json` anywhere in the tree.
TIMELINE_DIRNAME = "timeline"
TIMELINE_FILENAME = "song.timeline.json"
RECEIPT_FILENAME = "compile-receipt.json"

#: The three analysis stages, named so that a new observation kind would be a
#: new namespace rather than a schema change.
MEASURE_STAGE: Final = "activity.measure"
INTERVAL_STAGE: Final = "activity.interval"
ONSET_STAGE: Final = "onset.spectral_flux"

#: The three event types gate 4 admits, and the order they sort in when two
#: events share a start time. Fixed here rather than derived from a set, because
#: "deterministic ordering" is a requirement and set iteration is not one.
EVENT_ORDER: Final[dict[str, int]] = {
    "activity.sample": 0,
    "activity.interval": 1,
    "onset": 2,
}

#: How far a stem's duration may differ from the source's before this stage
#: refuses. The separation resamples 48 kHz to the model's 44.1 kHz, so an exact
#: match is not expected; fifty milliseconds is two activity windows and is far
#: larger than any rounding this pipeline performs.
DURATION_TOLERANCE_S: Final = 0.05

#: Everything that changes an event, in one place, so that the provenance and
#: the cache key are the same information. `docs/provenance.md` requires that:
#: a stage that cannot enumerate its parameters cannot be cached.
#:
#: Split into three groups and then recombined, because each analysis stage
#: records only what actually affected *it*. A parameter listed under a stage
#: that does not read it is a parameter a later reader will waste time on.
SHARED_PARAMETERS: Final[dict[str, Any]] = {
    "downmix": "channel_mean",
    "silence_floor_dbfs": SILENCE_FLOOR_DBFS,
    "rounding": {
        "time_places": TIME_PLACES,
        "db_places": DB_PLACES,
        "amplitude_places": AMPLITUDE_PLACES,
        "flux_places": FLUX_PLACES,
    },
}

MEASURE_PARAMETERS: Final[dict[str, Any]] = {
    "window_samples": ACTIVITY_WINDOW_SAMPLES,
    "hop_samples": ACTIVITY_HOP_SAMPLES,
    **SHARED_PARAMETERS,
}

INTERVAL_PARAMETERS: Final[dict[str, Any]] = {
    "window_samples": ACTIVITY_WINDOW_SAMPLES,
    "hop_samples": ACTIVITY_HOP_SAMPLES,
    "enter_dbfs": ACTIVITY_ENTER_DBFS,
    "exit_dbfs": ACTIVITY_EXIT_DBFS,
    "min_duration_s": ACTIVITY_MIN_DURATION_S,
    "merge_gap_s": ACTIVITY_MERGE_GAP_S,
    "rule": (
        "enter at or above enter_dbfs, leave below exit_dbfs, merge runs separated by less "
        "than merge_gap_s, then discard what is shorter than min_duration_s"
    ),
    **SHARED_PARAMETERS,
}

ONSET_PARAMETERS: Final[dict[str, Any]] = {
    "fft_samples": ONSET_FFT_SAMPLES,
    "hop_samples": ONSET_HOP_SAMPLES,
    "window": "hann_periodic",
    "novelty": "half_wave_rectified_spectral_flux_l1",
    "median_radius_frames": ONSET_MEDIAN_RADIUS_FRAMES,
    "peak_radius_frames": ONSET_PEAK_RADIUS_FRAMES,
    "median_multiplier": ONSET_MEDIAN_MULTIPLIER,
    "flux_floor": ONSET_FLUX_FLOOR,
    "min_gap_s": ONSET_MIN_GAP_S,
    "temporal_resolution": "one hop; no onset is more precise than hop_samples / sample_rate",
    "rule": (
        "a frame is an onset when its flux is the largest within peak_radius_frames, is at "
        "least median_multiplier times the local median plus flux_floor, and is at least "
        "min_gap_s after the previous accepted onset"
    ),
    **SHARED_PARAMETERS,
}

#: The whole parameter set, as the cache key sees it. One value per stage, so a
#: change to any of them is a different key and a different question.
ANALYSIS_PARAMETERS: Final[dict[str, Any]] = {
    MEASURE_STAGE: MEASURE_PARAMETERS,
    INTERVAL_STAGE: INTERVAL_PARAMETERS,
    ONSET_STAGE: ONSET_PARAMETERS,
}


class CompileError(Exception):
    """Compilation could not proceed, or produced something that failed its own checks."""


# ---------------------------------------------------------------------------
# The plan: every refusal, before a sample is read.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StemInput:
    """One model output this compile will read, verified against two records."""

    model_output: str
    path: Path
    relative_path: str
    hash: str
    duration_s: float
    sample_rate_hz: int
    channels: int


@dataclass(frozen=True)
class CompilePlan:
    """A fully resolved request to compile one accepted separation."""

    specimen_id: str
    repository_root: Path

    manifest: SeparationManifest
    manifest_path: Path
    manifest_hash: str

    specimen_review: SpecimenReview
    specimen_review_hash: str
    separation_review: SeparationReview
    separation_review_hash: str

    source_path: Path
    source_hash: str

    stems: tuple[StemInput, ...]
    output_dir: Path
    timeline_path: Path
    receipt_path: Path

    cache_key_inputs: Extension
    cache_key: str
    notices: tuple[str, ...]

    @property
    def tool(self) -> str:
        return "spectral_loom.analysis"

    @property
    def tool_revision(self) -> str:
        return f"spectral-loom=={__version__} numpy=={np.__version__}"

    def relative(self, path: Path) -> str:
        return str(path.relative_to(self.repository_root))


def runtime_identity() -> str:
    """The runtime a receipt records. No accelerator: this stage is arithmetic."""
    version = ".".join(platform.python_version_tuple()[:2])
    return f"cpython{version} {platform.system().lower()}-{platform.machine()}"


def plan(specimen_id: str, repository_root: Path) -> CompilePlan:
    """Resolve a compile request, or refuse with the reason.

    The order of the checks is the order a person would want to hear about
    them: is there a separation at all, did anyone accept the audio, did anyone
    accept *this* separation, are the files it describes actually here and
    unchanged, and do they line up with the recording they claim to be about.
    """
    manifest_path = (
        repository_root
        / DERIVED_DIRNAME
        / specimen_id
        / SEPARATION_DIRNAME
        / SEPARATION_MANIFEST_FILENAME
    )
    if not manifest_path.is_file():
        raise CompileError(
            f"no separation manifest at {manifest_path}. Compilation reads stems that already "
            f"exist; run `spectral-loom separate {specimen_id}` first."
        )
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = load_separation_manifest(manifest_path)
    except (OSError, SeparationError) as exc:
        raise CompileError(str(exc)) from exc
    manifest_hash = hash_bytes(manifest_bytes)

    source_path = repository_root / manifest.source_path
    if not source_path.is_file():
        raise CompileError(
            f"the separated source is not at {manifest.source_path}. The timeline this stage "
            f"would write is a set of claims about that recording, and a claim about a file "
            f"nobody holds cannot be checked by anybody."
        )
    source_hash = hash_file(source_path)
    if source_hash != manifest.source_audio.hash:
        raise CompileError(
            f"{manifest.source_path} hashes to {source_hash}, and the separation was performed "
            f"on {manifest.source_audio.hash}. These stems are not about the recording on disk."
        )

    try:
        specimen_review, specimen_review_path = require_accepted(
            repository_root, specimen_id, source_hash
        )
        separation_review, separation_review_path = require_separation_accepted(
            repository_root, specimen_id, manifest_hash
        )
    except ReviewError as exc:
        raise CompileError(str(exc)) from exc

    stems = _verify_stems(repository_root, manifest, separation_review)
    notices = _alignment_notices(manifest, stems)

    cache_key_inputs: Extension = {
        "tool": "spectral_loom.analysis",
        "tool_version": __version__,
        "numpy_version": str(np.__version__),
        "timeline_schema": f"{TIMELINE_SCHEMA_ID}/{TIMELINE_SCHEMA_VERSION}",
        "source_hash": source_hash,
        "separation_manifest_hash": manifest_hash,
        # By model output name rather than positionally: the separator's own
        # order is stable, but a key that depended on it would silently change
        # meaning if a future bag emitted its sources in another order.
        "stem_hashes": {stem.model_output: stem.hash for stem in stems},
        "parameters": ANALYSIS_PARAMETERS,
    }

    output_dir = repository_root / DERIVED_DIRNAME / specimen_id / TIMELINE_DIRNAME
    return CompilePlan(
        specimen_id=specimen_id,
        repository_root=repository_root,
        manifest=manifest,
        manifest_path=manifest_path,
        manifest_hash=manifest_hash,
        specimen_review=specimen_review,
        specimen_review_hash=hash_file(specimen_review_path),
        separation_review=separation_review,
        separation_review_hash=hash_file(separation_review_path),
        source_path=source_path,
        source_hash=source_hash,
        stems=stems,
        output_dir=output_dir,
        timeline_path=output_dir / TIMELINE_FILENAME,
        receipt_path=output_dir / RECEIPT_FILENAME,
        cache_key_inputs=cache_key_inputs,
        cache_key=compute_cache_key(cache_key_inputs),
        notices=notices,
    )


def _verify_stems(
    repository_root: Path, manifest: SeparationManifest, review: SeparationReview
) -> tuple[StemInput, ...]:
    """Every model output, checked against the manifest *and* against the review.

    Both, because they answer different questions. The manifest says what the
    separator emitted; the review says what a person heard. A file that matches
    one and not the other is a file this stage has no business reading, and
    which of the two it disagrees with is worth knowing.
    """
    reviewed = {
        artifact.name: artifact.hash
        for artifact in review.reviewed_artifacts
        if artifact.kind == "model_output"
    }
    verified: list[StemInput] = []
    for name in manifest.separator.sources:
        stem = next((s for s in manifest.stems if s.model_output == name), None)
        if stem is None:
            raise CompileError(
                f"the separator emits {manifest.separator.sources} and the manifest has no "
                f"{name!r} stem; the record is internally inconsistent"
            )
        target = repository_root / stem.audio.path
        if not target.is_file():
            raise CompileError(
                f"{stem.audio.path} is declared by the separation manifest and is not on disk. "
                f"Re-run `spectral-loom separate`; a timeline compiled from stems that are not "
                f"there would be a timeline about nothing."
            )
        found = hash_file(target)
        if found != stem.audio.hash:
            raise CompileError(
                f"{stem.audio.path} hashes to {found}, and the separation manifest recorded "
                f"{stem.audio.hash}. These are not the bytes that were separated."
            )
        if reviewed.get(name) != found:
            raise CompileError(
                f"{stem.audio.path} hashes to {found}, and the accepted separation review "
                f"records {reviewed.get(name, 'nothing')} for the {name!r} output. A human "
                f"verdict does not transfer to bytes that human did not hear."
            )
        verified.append(
            StemInput(
                model_output=name,
                path=target,
                relative_path=stem.audio.path,
                hash=found,
                duration_s=stem.audio.duration_s,
                sample_rate_hz=stem.audio.sample_rate_hz,
                channels=stem.audio.channels,
            )
        )
    return tuple(verified)


def _alignment_notices(
    manifest: SeparationManifest, stems: tuple[StemInput, ...]
) -> tuple[str, ...]:
    """Refuse on incompatible timing; merely say so when something is odd.

    A stem whose duration does not match the recording cannot be placed on the
    recording's timeline at all, so that is a refusal. A nonzero temporal offset
    between the summed outputs and the source is a different thing: it is a
    number the separation already measured, this project has no threshold for
    it, and inventing one here would be asserting a pass mark nobody has earned.
    It is surfaced instead.
    """
    source_duration = manifest.source_audio.duration_s
    for stem in stems:
        if abs(stem.duration_s - source_duration) > DURATION_TOLERANCE_S:
            raise CompileError(
                f"{stem.relative_path} is {stem.duration_s:.3f} s and the source recording is "
                f"{source_duration:.3f} s. Every event this stage writes is a time on the "
                f"source's timeline, and these two cannot be placed on one timeline."
            )
    rates = {stem.sample_rate_hz for stem in stems}
    if len(rates) != 1:
        raise CompileError(f"the stems disagree about their sample rate: {sorted(rates)}")

    notices: list[str] = []
    for diagnostic in manifest.diagnostics:
        lag = diagnostic.measurements.get("peak_alignment_lag_samples")
        if isinstance(lag, int | float) and lag != 0:
            notices.append(
                f"the separation measured a {lag}-sample offset between the summed outputs and "
                f"the source; every event time here is relative to the stems, so a nonzero "
                f"offset means they are relative to the source only approximately"
            )
    return tuple(notices)


# ---------------------------------------------------------------------------
# The build receipt: everything that must not be in the timeline.
# ---------------------------------------------------------------------------


class CompileReceipt(BaseModel):
    """What one compile run did, kept out of the artifact it produced.

    Not a published contract, and the omission is the point. `schemas/` is what
    another implementation reads; this is a local build record. It exists so
    that the timeline can stay byte-identical while the facts a person actually
    wants when a cache misbehaves — when it ran, how long it took, what it
    verified — are still written down somewhere.
    """

    model_config = ConfigDict(extra="forbid")

    specimen_id: str
    timeline_path: str
    timeline_sha256: str

    cache_key: str
    cache_key_inputs: dict[str, Any]

    source_hash: str
    specimen_review_hash: str
    separation_manifest_hash: str
    separation_review_hash: str
    stem_hashes: dict[str, str]

    tool: str
    tool_revision: str
    runtime: str
    started_at: datetime
    duration_ms: int
    event_counts: dict[str, dict[str, int]]
    notices: list[str] = []


def write_receipt(path: Path, receipt: CompileReceipt) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_receipt(path: Path) -> CompileReceipt:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompileError(f"cannot read {path}: {exc}") from exc
    try:
        return CompileReceipt.model_validate(document)
    except ValidationError as exc:
        raise CompileError(f"{path} is not a valid compile receipt: {exc}") from exc


def cache_miss_reason(plan: CompilePlan, receipt: CompileReceipt) -> str | None:
    """Why an existing timeline may not be reused, or None if it may be.

    Prose rather than a boolean, for the reason `docs/provenance.md` gives: a
    run that should have hit cache and did not is a bug report, and a silent
    miss is the cheapest possible way to hide an unstable key.

    The inputs were already re-hashed by :func:`plan`, so what is left to check
    is the *output*: that the declared timeline is present and is still the
    document this receipt describes.
    """
    if receipt.cache_key != plan.cache_key:
        return (
            f"cache key differs: recorded {receipt.cache_key}, computed {plan.cache_key}. "
            f"Something in the stems, the tool, or the parameters is not what it was."
        )
    if receipt.stem_hashes != {stem.model_output: stem.hash for stem in plan.stems}:
        return "the stems on disk are not the ones this receipt was written for"
    if not plan.timeline_path.is_file():
        return f"the declared output is missing: {plan.relative(plan.timeline_path)}"
    found = hash_file(plan.timeline_path)
    if found != receipt.timeline_sha256:
        return (
            f"{plan.relative(plan.timeline_path)} hashes to {found}, and the receipt recorded "
            f"{receipt.timeline_sha256}; a receipt describing a document that has since changed "
            f"is not a cache entry"
        )
    return None


def reusable(plan: CompilePlan) -> tuple[SongTimeline, CompileReceipt] | None:
    """A complete, verified previous result for exactly this request, or None."""
    if not plan.receipt_path.is_file():
        return None
    try:
        receipt = load_receipt(plan.receipt_path)
    except CompileError:
        return None
    if cache_miss_reason(plan, receipt) is not None:
        return None
    try:
        return load_timeline(plan.timeline_path), receipt
    except CompileError:
        return None


def load_timeline(path: Path) -> SongTimeline:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompileError(f"cannot read {path}: {exc}") from exc
    try:
        return SongTimeline.model_validate(document)
    except ValidationError as exc:
        raise CompileError(f"{path} is not a valid song timeline: {exc}") from exc


# ---------------------------------------------------------------------------
# Canonical bytes.
# ---------------------------------------------------------------------------


def canonical_bytes(timeline: SongTimeline) -> bytes:
    """The one serialization of a timeline this project writes.

    Sorted keys, two-space indent, one trailing newline, UTF-8. Named and used
    everywhere rather than inlined, because "byte-identical across
    recompilations" is a property of *this function* plus the determinism of
    what it is handed, and a second serialization site would be a second place
    for the property to stop holding.
    """
    document = timeline.model_dump(mode="json")
    return (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


# ---------------------------------------------------------------------------
# The compile.
# ---------------------------------------------------------------------------


def build_timeline(plan: CompilePlan) -> SongTimeline:
    """Read every stem, run the three analyses, and assemble the document.

    Pure with respect to the filesystem except for reading the stems, and free
    of clocks entirely: nothing in here can observe what time it is, which is
    the cheapest available guarantee that nothing in here can put the time into
    the artifact.
    """
    tracks: list[Track] = []
    measure_inputs: dict[str, str] = {}
    variant = plan.manifest.separator.weights_variant

    for stem in plan.stems:
        try:
            audio = read_wav_mono(stem.path)
        except AnalysisError as exc:
            raise CompileError(str(exc)) from exc

        measurement = measure_activity(audio)
        intervals = infer_intervals(measurement)
        onsets = infer_onsets(audio)

        evidence_for = {
            stage: Evidence(artifact=stem.relative_path, artifact_hash=stem.hash, stage=stage)
            for stage in (MEASURE_STAGE, INTERVAL_STAGE, ONSET_STAGE)
        }
        window_s = quantize(measurement.window_s, TIME_PLACES)
        events: list[Event] = []

        for index in range(len(measurement)):
            start = quantize(float(measurement.start_s[index]), TIME_PLACES)
            events.append(
                Event(
                    type="activity.sample",
                    start_s=start,
                    end_s=quantize(start + measurement.window_s, TIME_PLACES),
                    evidence=evidence_for[MEASURE_STAGE],
                    payload={
                        "rms": quantize(float(measurement.rms[index]), AMPLITUDE_PLACES),
                        "rms_dbfs": quantize(float(measurement.rms_dbfs[index]), DB_PLACES),
                        "peak": quantize(float(measurement.peak[index]), AMPLITUDE_PLACES),
                        "analysis_window_s": window_s,
                    },
                )
            )

        for interval in intervals:
            events.append(
                Event(
                    type="activity.interval",
                    start_s=interval.start_s,
                    end_s=interval.end_s,
                    evidence=evidence_for[INTERVAL_STAGE],
                    payload={
                        "frames": interval.frames,
                        "min_rms_dbfs": interval.min_rms_dbfs,
                        "max_rms_dbfs": interval.max_rms_dbfs,
                        "mean_rms_dbfs": interval.mean_rms_dbfs,
                        "merged_gaps": interval.merged_gaps,
                        "enter_dbfs": ACTIVITY_ENTER_DBFS,
                        "exit_dbfs": ACTIVITY_EXIT_DBFS,
                    },
                )
            )

        resolution_s = quantize(onsets.resolution_s, TIME_PLACES)
        for onset in onsets.onsets:
            events.append(
                Event(
                    type="onset",
                    start_s=onset.start_s,
                    # No confidence, on purpose. Spectral flux is not a
                    # probability and has no calibration; scaling it into
                    # [0, 1] would manufacture one out of arithmetic.
                    evidence=evidence_for[ONSET_STAGE],
                    payload={
                        "flux": onset.flux,
                        "threshold": onset.threshold,
                        "margin": onset.margin,
                        "local_median": onset.local_median,
                        "frame_rms_dbfs": onset.frame_rms_dbfs,
                        "temporal_resolution_s": resolution_s,
                    },
                )
            )

        events.sort(key=lambda e: (e.start_s, EVENT_ORDER[e.type], e.end_s or e.start_s))
        measure_inputs[stem.model_output] = stem.hash
        tracks.append(
            Track(
                id=f"{variant}.{stem.model_output}",
                source=stem.relative_path,
                role=f"{variant} model output: {stem.model_output}",
                events=events,
            )
        )

    return SongTimeline(
        specimen_id=plan.specimen_id,
        source_audio=plan.manifest.source_audio,
        provenance=_provenance(plan, measure_inputs),
        tracks=tracks,
    )


def _provenance(plan: CompilePlan, stem_hashes: dict[str, str]) -> list[Provenance]:
    """The whole lineage, in production order, with the layers kept apart.

    The generation and separation stages are copied verbatim from the records
    that already carry them, rather than restated: the prompt stays labelled
    ``requested``, the separator's opinion stays labelled ``inferred``, and the
    stems stop appearing from nowhere. Their timestamps are historical facts
    about runs that already happened and are stable, so copying them costs the
    document nothing in determinism.

    The three analysis stages carry no ``started_at`` and no ``duration_ms``.
    That is not an omission — those are the two fields that would make this
    document different every time it was produced from identical inputs.
    """
    upstream = list(plan.specimen_review.provenance) + list(plan.manifest.provenance)
    stages = [entry.stage for entry in upstream]
    repeated = {s for s in stages if stages.count(s) > 1}
    if repeated:
        raise CompileError(
            f"the generation and separation records both claim the stage(s) {sorted(repeated)}. "
            f"A timeline's provenance is one stage per producing step, and two entries under "
            f"one name would make it impossible to say which of them an event cites."
        )
    collision = set(stages) & {MEASURE_STAGE, INTERVAL_STAGE, ONSET_STAGE}
    if collision:
        raise CompileError(
            f"an upstream record already uses this stage's name: {sorted(collision)}"
        )

    return [
        *upstream,
        Provenance(
            stage=MEASURE_STAGE,
            tool=plan.tool,
            tool_revision=plan.tool_revision,
            # Short-time RMS and peak over a stated window. Anybody holding the
            # same file and the same window gets the same numbers, which is
            # what `observed` means and what separates this from the two below.
            truth_layer=TruthLayer.OBSERVED,
            input_hashes=dict(stem_hashes),
            parameters=dict(MEASURE_PARAMETERS),
            runtime=None,
        ),
        Provenance(
            stage=INTERVAL_STAGE,
            tool=plan.tool,
            tool_revision=plan.tool_revision,
            truth_layer=TruthLayer.INFERRED,
            input_hashes=dict(stem_hashes),
            parameters=dict(INTERVAL_PARAMETERS),
            runtime=None,
        ),
        Provenance(
            stage=ONSET_STAGE,
            tool=plan.tool,
            tool_revision=plan.tool_revision,
            truth_layer=TruthLayer.INFERRED,
            input_hashes=dict(stem_hashes),
            parameters=dict(ONSET_PARAMETERS),
            runtime=None,
        ),
    ]


def event_counts(timeline: SongTimeline) -> dict[str, dict[str, int]]:
    """Per track, how many of each event type. Descriptive; never a verdict."""
    counts: dict[str, dict[str, int]] = {}
    for track in timeline.tracks:
        per_type = dict.fromkeys(EVENT_ORDER, 0)
        for event in track.events:
            per_type[event.type] = per_type.get(event.type, 0) + 1
        counts[track.id] = per_type
    return counts


def workspace(plan: CompilePlan) -> Path:
    """A private directory to build in, beside where the result will land."""
    return plan.output_dir.with_name(f".{TIMELINE_DIRNAME}.partial.{os.getpid()}")


def compile_timeline(
    plan: CompilePlan, *, force: bool = False
) -> tuple[SongTimeline, CompileReceipt, bool]:
    """Compile once, or reuse a verified previous result. Returns whether it is new."""
    if not force:
        existing = reusable(plan)
        if existing is not None:
            timeline, receipt = existing
            return timeline, receipt, False

    started = datetime.now(UTC)
    clock = time.monotonic()
    timeline = build_timeline(plan)
    payload = canonical_bytes(timeline)
    elapsed_ms = int((time.monotonic() - clock) * 1000)

    built = workspace(plan)
    if built.exists():
        shutil.rmtree(built)
    built.mkdir(parents=True)
    try:
        (built / TIMELINE_FILENAME).write_bytes(payload)
        receipt = CompileReceipt(
            specimen_id=plan.specimen_id,
            timeline_path=plan.relative(plan.timeline_path),
            timeline_sha256=hash_bytes(payload),
            cache_key=plan.cache_key,
            cache_key_inputs=dict(plan.cache_key_inputs),
            source_hash=plan.source_hash,
            specimen_review_hash=plan.specimen_review_hash,
            separation_manifest_hash=plan.manifest_hash,
            separation_review_hash=plan.separation_review_hash,
            stem_hashes={stem.model_output: stem.hash for stem in plan.stems},
            tool=plan.tool,
            tool_revision=plan.tool_revision,
            runtime=runtime_identity(),
            started_at=started,
            duration_ms=elapsed_ms,
            event_counts=event_counts(timeline),
            notices=list(plan.notices),
        )
        write_receipt(built / RECEIPT_FILENAME, receipt)
    except Exception:
        shutil.rmtree(built, ignore_errors=True)
        raise

    try:
        _clear_output_dir(plan)
    except Exception:
        shutil.rmtree(built, ignore_errors=True)
        raise
    plan.output_dir.parent.mkdir(parents=True, exist_ok=True)
    os.replace(built, plan.output_dir)
    return timeline, receipt, True


def _clear_output_dir(plan: CompilePlan) -> None:
    """Make room for the result, refusing to destroy bytes this stage did not write.

    Proportionate rather than uniform. A previous *compile* is regenerable in
    seconds from inputs that are already verified, so replacing one is not a
    loss and does not need a flag. Anything else in that directory — a partial
    run from another version, a file somebody put there — is evidence about
    something, and this stage stops rather than deleting it.
    """
    if not plan.output_dir.exists():
        return
    if not plan.output_dir.is_dir():
        raise CompileError(f"{plan.output_dir} exists and is not a directory")
    if not plan.receipt_path.is_file():
        raise CompileError(
            f"{plan.output_dir} already exists and has no {RECEIPT_FILENAME} in it, so it is "
            f"not something this stage wrote. Those bytes are not deleted: inspect them, or "
            f"move them somewhere else."
        )
    load_receipt(plan.receipt_path)  # raises, with the path, if it is not one of ours
    shutil.rmtree(plan.output_dir)
