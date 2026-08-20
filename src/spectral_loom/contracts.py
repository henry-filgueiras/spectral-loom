"""Versioned data contracts for the Spectral Loom compiler boundary.

Three documents matter, and they are deliberately small:

``SongSpec``
    What was *asked for*. A specification is authored before any audio exists,
    so every musical field on it is a request and is named ``requested_*`` to
    keep that visible at the call site. A specification is never evidence about
    a recording; see ``archaeology/principles/0001``.

``SongTimeline``
    What was *observed or inferred from* a recording. The timeline is the
    language-neutral compiler boundary (``archaeology/decisions/0003``): every
    downstream projection reads this file, and no projection may write to it.

``GenerationManifest``
    What one generator was asked and what came back. It sits beside a generated
    audio file, which is untracked, and it is the only thing that makes that
    file attributable to a specification and a revision. It carries observations
    about the file and the *request* that produced it, and never the request
    dressed up as an observation.

All three carry an explicit ``schema_id`` and ``schema_version``. The version is a
``Literal``, on purpose: bumping it is a code change with a reviewable diff and
a regenerated JSON Schema, rather than a string that silently drifts. Documents
on disk outlive the code that wrote them, so a field may gain meaning additively
but may never quietly change meaning under an unchanged version.

Scope discipline for the timeline, restated because it is easy to lose:

- It records musical observations. Never geometry, colour, shaders, camera
  behaviour, layer order, or any other rendering instruction.
- The event vocabulary is intentionally open. Early events are expected to be
  ``activity.sample``, ``activity.interval`` and ``onset``; notes arrive later.
  Chords, sections, lyrics, and engraving are not modelled, and modelling them
  now would be inventing an ontology instead of observing one (``dragon:1``).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

SPEC_SCHEMA_ID: Final = "spectral-loom/song-spec"
SPEC_SCHEMA_VERSION: Final = "0.1.0"

TIMELINE_SCHEMA_ID: Final = "spectral-loom/song-timeline"
TIMELINE_SCHEMA_VERSION: Final = "0.1.0"

GENERATION_SCHEMA_ID: Final = "spectral-loom/generation-manifest"
GENERATION_SCHEMA_VERSION: Final = "0.1.0"

#: Slug-shaped stable identifier for a specimen. Stable across regeneration:
#: it names the *intent*, while the audio hash names a particular rendering.
SpecimenId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")]

#: A content hash, algorithm-prefixed so a future migration is legible.
ContentHash = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]

#: Dotted, lowercase namespace. Used for event types and stage names so that a
#: new event kind is an additive namespace rather than a schema change.
Namespaced = Annotated[str, Field(pattern=r"^[a-z][a-z0-9]*(\.[a-z0-9_]+)*$", max_length=64)]

#: An open extension bag. Contained on purpose: generator- or tool-specific
#: parameters live in exactly one place instead of leaking into the envelope.
Extension = dict[str, JsonValue]


class Contract(BaseModel):
    """Base for every contract model: unknown fields are an error.

    ``extra="forbid"`` is the point of having a contract. A typo in a field name
    must fail loudly rather than being silently dropped and later missed. The
    designated escape hatches are the explicit extension bags.
    """

    model_config = ConfigDict(extra="forbid")


class TruthLayer(StrEnum):
    """Where a value came from. These never collapse into one another.

    ``requested``
        Authored before the audio existed. A prompt, a seed, a target BPM.
    ``observed``
        Measurable from the artifact by anyone holding it. A duration, a hash.
    ``inferred``
        A named model's opinion at an exact revision, with a confidence.
    ``corrected``
        A human override, recorded as its own stage rather than as an edit that
        erases the inference it replaced.
    """

    REQUESTED = "requested"
    OBSERVED = "observed"
    INFERRED = "inferred"
    CORRECTED = "corrected"


# ---------------------------------------------------------------------------
# Song specification: the requested layer.
# ---------------------------------------------------------------------------


class GeneratorRef(Contract):
    """Which generator was asked, and at exactly which revision."""

    adapter: str = Field(
        min_length=1,
        max_length=64,
        description="Adapter name within this project, e.g. 'ace-step'. Not a package name.",
    )
    model_id: str = Field(
        min_length=1,
        max_length=200,
        description="Upstream model identity, e.g. a Hugging Face repository id.",
    )
    revision: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Exact upstream revision: a commit sha, never a moving branch or tag. "
            "Null means the revision is not pinned yet, and a null revision must "
            "block generation rather than resolve to whatever is current today."
        ),
    )

    @property
    def is_pinned(self) -> bool:
        """Whether this specimen could be generated reproducibly."""
        return self.revision is not None


class SongSpec(Contract):
    """A request for a specimen. Nothing here is an observation about audio."""

    schema_id: Literal["spectral-loom/song-spec"] = SPEC_SCHEMA_ID
    schema_version: Literal["0.1.0"] = SPEC_SCHEMA_VERSION

    specimen_id: SpecimenId = Field(
        description="Stable identifier for this specimen, independent of any rendering of it."
    )
    generator: GeneratorRef

    requested_prompt: str = Field(
        min_length=1,
        max_length=4000,
        description="Natural-language request. A request, not a description of the result.",
    )
    seed: int = Field(
        ge=0, description="Generator seed. Part of reproducibility, not of musical truth."
    )
    requested_duration_s: float = Field(
        gt=0,
        le=3600,
        description="Requested duration in seconds. The rendered audio may differ.",
    )

    requested_bpm: float | None = Field(default=None, gt=0, le=400)
    requested_key: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Requested key or scale as free text, e.g. 'D minor'. Deliberately unmodelled: "
            "there is no key ontology in this project yet, and inventing one here would "
            "outrun the evidence."
        ),
    )
    requested_time_signature: str | None = Field(default=None, pattern=r"^[1-9][0-9]?/[1-9][0-9]?$")
    requested_instruments: list[str] | None = Field(
        default=None,
        max_length=32,
        description=(
            "Instruments the prompt asks for. Their presence in the result is an open "
            "question that only analysis of the audio can answer."
        ),
    )

    generator_params: Extension = Field(
        default_factory=dict,
        description="Generator-specific parameters, contained here rather than in the envelope.",
    )
    notes: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Song timeline: the observed and inferred layers.
# ---------------------------------------------------------------------------


class SourceAudio(Contract):
    """The evidence-bearing artifact this timeline is about."""

    hash: ContentHash = Field(description="Hash of the exact audio bytes the stages consumed.")
    duration_s: float = Field(gt=0, description="Observed duration of that audio.")
    sample_rate_hz: int | None = Field(default=None, gt=0)
    channels: int | None = Field(default=None, ge=1, le=64)


class Provenance(Contract):
    """One producing stage, recorded so its output can be attributed and recomputed.

    A stage entry answers: which inputs, which tool at which exact revision, with
    which parameters, on which runtime, for how long, emitting which artifacts,
    and at which truth layer. Together with the input hashes it is also the
    cache key: an entry whose key cannot be recomputed is garbage, not a cache.
    """

    stage: Namespaced = Field(
        description="Stage name, unique within a timeline, e.g. 'separation' or 'onsets.bass'."
    )
    tool: str = Field(min_length=1, max_length=200, description="Tool or model identity.")
    tool_revision: str = Field(
        min_length=1,
        max_length=200,
        description="Exact revision of that tool: a version plus commit, never a branch.",
    )
    truth_layer: TruthLayer

    input_hashes: dict[str, ContentHash] = Field(
        default_factory=dict,
        description="Role name to content hash for every input this stage consumed.",
    )
    parameters: Extension = Field(
        default_factory=dict,
        description="Parameters that affected the result, and therefore the cache key.",
    )
    output_hashes: dict[str, ContentHash] = Field(
        default_factory=dict,
        description="Role name to content hash for every artifact this stage emitted.",
    )

    runtime: str | None = Field(
        default=None,
        max_length=200,
        description="Runtime and backend actually used, e.g. 'cpython3.11 macos-arm64 mps'.",
    )
    started_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class Evidence(Contract):
    """What an event is grounded in.

    The event's own ``start_s``/``end_s`` are the source interval; this names the
    artifact that interval belongs to and the stage that read it. An event with
    no traceable evidence is an assertion, and this contract has no room for one.
    """

    artifact: str = Field(
        min_length=1,
        max_length=256,
        description="Artifact this observation came from, e.g. 'source' or 'stems/bass.wav'.",
    )
    artifact_hash: ContentHash | None = None
    stage: Namespaced = Field(
        description="Name of the producing stage in this timeline's provenance."
    )


class Event(Contract):
    """A generic timed observation.

    The vocabulary is open: ``type`` is a namespaced string rather than an enum,
    so a new kind of observation is a new namespace and not a schema change.
    Anything specific to a kind lives in ``payload`` under that same namespace.
    """

    type: Namespaced = Field(
        description="Namespaced event type, e.g. 'activity.sample', 'activity.interval', 'onset'."
    )
    start_s: float = Field(ge=0, description="Start time in the timeline's time unit.")
    end_s: float | None = Field(default=None, ge=0, description="End time; absent for instants.")
    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description=(
            "Producer's confidence, where the producer reports one. Absence of an event is "
            "never evidence of absence in the audio; see docs/architecture.md."
        ),
    )
    evidence: Evidence
    payload: Extension = Field(
        default_factory=dict,
        description="Type-specific data, keyed within the event type's own namespace.",
    )

    @model_validator(mode="after")
    def _check_interval(self) -> Event:
        if self.end_s is not None and self.end_s < self.start_s:
            raise ValueError(
                f"event ends before it starts: start_s={self.start_s} end_s={self.end_s}"
            )
        return self


class Track(Contract):
    """A logical stream of observations, usually but not necessarily one stem."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$", description="Unique within a timeline.")
    source: str = Field(
        min_length=1,
        max_length=256,
        description="Artifact these observations came from, e.g. 'mix' or 'stems/drums.wav'.",
    )
    role: str | None = Field(
        default=None,
        max_length=64,
        description="Free-text role, e.g. 'bass'. A label for humans, not a taxonomy.",
    )
    events: list[Event] = Field(default_factory=list)


class SongTimeline(Contract):
    """The compiler boundary artifact: what was observed or inferred about one recording."""

    schema_id: Literal["spectral-loom/song-timeline"] = TIMELINE_SCHEMA_ID
    schema_version: Literal["0.1.0"] = TIMELINE_SCHEMA_VERSION

    specimen_id: SpecimenId
    source_audio: SourceAudio
    time_unit: Literal["seconds"] = Field(
        default="seconds",
        description="Explicit, because a timeline read years later must not have to guess.",
    )

    provenance: list[Provenance] = Field(
        min_length=1,
        description="Every stage that contributed to this document, in production order.",
    )
    tracks: list[Track] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_references(self) -> SongTimeline:
        stages = [p.stage for p in self.provenance]
        duplicate_stages = {s for s in stages if stages.count(s) > 1}
        if duplicate_stages:
            raise ValueError(f"duplicate provenance stage names: {sorted(duplicate_stages)}")

        track_ids = [t.id for t in self.tracks]
        duplicate_tracks = {t for t in track_ids if track_ids.count(t) > 1}
        if duplicate_tracks:
            raise ValueError(f"duplicate track ids: {sorted(duplicate_tracks)}")

        known = set(stages)
        for track in self.tracks:
            for index, event in enumerate(track.events):
                if event.evidence.stage not in known:
                    raise ValueError(
                        f"track '{track.id}' event {index} cites evidence stage "
                        f"'{event.evidence.stage}', which is not in this timeline's provenance"
                    )
        return self


# ---------------------------------------------------------------------------
# Generation manifest: what a generator was asked, and what came back.
# ---------------------------------------------------------------------------


class GenerationManifest(Contract):
    """The record that makes one generated audio file auditable.

    Written beside the audio, which is untracked, so this is what answers the
    seven questions in ``docs/provenance.md`` about a file nobody can regenerate
    from memory.

    The truth-layer rule does the most work here, because generation is exactly
    where it is easiest to break. The prompt asked for 96 BPM in D minor with an
    electric bass. **None of that appears in this document as a fact about the
    audio.** What appears is:

    - ``source_audio``: hash, duration, sample rate, channel count. Observed,
      measurable by anyone holding the file.
    - ``provenance``: one stage at ``truth_layer: requested``, whose
      ``parameters`` carry the prompt, the seed, and every value handed to the
      generator — labelled as the request they are.
    - ``spec_hash``: the exact bytes of the specification that was read, so the
      whole request is recoverable without being restated here in a form that
      could be mistaken for a measurement.

    Whether the audio actually contains a bass is a question for a
    ``SongTimeline``, produced by analysing the audio. It is not answerable from
    this document and this document does not pretend otherwise. See
    ``archaeology/principles/0001``.
    """

    schema_id: Literal["spectral-loom/generation-manifest"] = GENERATION_SCHEMA_ID
    schema_version: Literal["0.1.0"] = GENERATION_SCHEMA_VERSION

    specimen_id: SpecimenId
    spec_path: str = Field(
        min_length=1,
        max_length=512,
        description=(
            "Where the specification was read from. A claim about where a file was, which is "
            "why `spec_hash` is beside it: only the hash survives the file being moved."
        ),
    )
    spec_hash: ContentHash = Field(
        description="Hash of the exact specification bytes that produced this artifact."
    )

    source_audio: SourceAudio = Field(
        description="Observed properties of the generated file. Measured, never requested."
    )

    provenance: list[Provenance] = Field(
        min_length=1,
        description=(
            "Every stage that contributed, in production order. The generating stage is "
            "`truth_layer: requested`: it emits evidence rather than a claim about evidence, "
            "and its parameters are what was asked for."
        ),
    )

    @model_validator(mode="after")
    def _check_stages(self) -> GenerationManifest:
        stages = [p.stage for p in self.provenance]
        duplicate = {s for s in stages if stages.count(s) > 1}
        if duplicate:
            raise ValueError(f"duplicate provenance stage names: {sorted(duplicate)}")
        return self
