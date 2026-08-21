"""Versioned data contracts for the Spectral Loom compiler boundary.

Six documents, and they are deliberately small:

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

``SeparationManifest``
    What one separator was given, what it emitted, and under exactly which
    identities. Its stems are named for the *model's own outputs*: ``bass``
    means HTDemucs assigned a signal to its ``bass`` output, and never that the
    file contains only bass or that the source contained a bass at all.

``SpecimenReview``
    What a human decided about one exact rendering after listening to it. It is
    tracked, unlike the audio it is about, so it is the only record that
    survives a clean clone of a gate having been passed by ears rather than by
    a program. It is keyed by the audio's hash, because a specimen id names an
    intent and two renderings of one intent are two different recordings.

``SeparationReview``
    What a human decided about one exact separation after listening to it. The
    same argument one layer down: a separation lives in a directory the next run
    will reuse, so the acceptance is bound to the separation manifest's own
    content hash and to every artifact in the exhibit, each by hash.

All six carry an explicit ``schema_id`` and ``schema_version``. The version is a
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

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

SPEC_SCHEMA_ID: Final = "spectral-loom/song-spec"
SPEC_SCHEMA_VERSION: Final = "0.1.0"

TIMELINE_SCHEMA_ID: Final = "spectral-loom/song-timeline"
TIMELINE_SCHEMA_VERSION: Final = "0.1.0"

GENERATION_SCHEMA_ID: Final = "spectral-loom/generation-manifest"
GENERATION_SCHEMA_VERSION: Final = "0.1.0"

REVIEW_SCHEMA_ID: Final = "spectral-loom/specimen-review"
REVIEW_SCHEMA_VERSION: Final = "0.1.0"

SEPARATION_SCHEMA_ID: Final = "spectral-loom/separation-manifest"
SEPARATION_SCHEMA_VERSION: Final = "0.1.0"

SEPARATION_REVIEW_SCHEMA_ID: Final = "spectral-loom/separation-review"
SEPARATION_REVIEW_SCHEMA_VERSION: Final = "0.1.0"

#: Slug-shaped stable identifier for a specimen. Stable across regeneration:
#: it names the *intent*, while the audio hash names a particular rendering.
SpecimenId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")]

#: A lowercase identifier for something this project names: a review criterion,
#: a stem, a diagnostic. Same shape as a specimen id, and deliberately not a
#: free string, so an identifier stays quotable in a path and a URL.
Slug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")]

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


# ---------------------------------------------------------------------------
# Specimen review: what a human decided about one exact rendering.
# ---------------------------------------------------------------------------


class CriterionResponse(StrEnum):
    """A reviewer's answer to one criterion.

    ``UNCLEAR`` exists so that a reviewer who could not tell is not forced to
    say "no". The distinction matters for the same reason it matters everywhere
    else in this project: not detecting something and establishing its absence
    are different claims.
    """

    YES = "yes"
    NO = "no"
    UNCLEAR = "unclear"


class ReviewCriterion(Contract):
    """One question a reviewer was asked, and what they answered.

    The question travels with the answer on purpose. A bare ``{"bass": "yes"}``
    read two years later is uninterpretable, and a criterion whose wording
    changed silently would make two reviews look comparable when they are not.
    """

    id: Slug = Field(description="Stable identifier for this criterion within its question set.")
    question: str = Field(
        min_length=1,
        max_length=500,
        description="Exactly what the reviewer was asked, in the wording they were asked it.",
    )
    response: CriterionResponse
    notes: str | None = Field(
        default=None,
        max_length=2000,
        description="The reviewer's own qualification of their answer, if they gave one.",
    )


class HumanReview(Contract):
    """A human's judgement about an artifact's fitness for a purpose.

    **This is deliberately not one of the four truth layers**, and the omission
    is the careful part. ``requested``, ``observed``, ``inferred`` and
    ``corrected`` classify *claims about a recording* by where the claim came
    from. "I accept these bytes as this project's first experimental specimen"
    is not a claim about the recording at all: it is a claim about the project.
    Nothing here says the audio contains a bass, a tempo, or a key.

    So a review is not a :class:`Provenance` entry either. A provenance entry
    records a stage so its output can be attributed and recomputed; a review
    emits no artifact and cannot be recomputed, and giving a person a
    ``tool_revision`` would be a fiction. See ``archaeology/decisions/0010``.

    What the answers *do* record is what a named person perceived on a named
    day. ``bass-audible-and-exposed: yes`` means the reviewer heard something
    they call an exposed bass. It does not establish that the source contains an
    electric bass, and no downstream stage may read it as though it did.
    """

    reviewer: str = Field(
        min_length=1, max_length=200, description="Who listened. A person, named."
    )
    reviewed_on: date = Field(
        description="The day they listened. A judgement is dated, not versioned."
    )
    method: str = Field(
        min_length=1,
        max_length=1000,
        description="How the artifact was reviewed, in enough detail to know what was not done.",
    )
    criteria: list[ReviewCriterion] = Field(
        min_length=1, description="Every question put to the reviewer, with their answer."
    )
    accepted: bool = Field(
        description=(
            "Whether the reviewer accepts these exact bytes for the purpose in `purpose`. "
            "Never a claim that any requested instrument, tempo, or key was established."
        )
    )
    purpose: str = Field(
        min_length=1,
        max_length=500,
        description="What acceptance would mean. Stated, so that it cannot be quietly widened.",
    )
    notes: str | None = Field(
        default=None,
        max_length=4000,
        description=(
            "Free prose. On a rejection this is where what was wrong goes, because a record "
            "that can only say yes is a marketing document."
        ),
    )


class SpecimenReview(Contract):
    """The tracked record that one human judged one exact rendering.

    The audio is untracked and regenerable; this document is tracked and is not.
    From a clean clone it is the only surviving statement that anybody ever
    listened, which is why it restates the observations rather than pointing at
    a manifest that may not be on the machine.

    **Keyed by the audio hash, not by the specimen id.** A specimen id names an
    intent and survives regeneration, so `sparse-funk-exposed-bass` may later
    point at bytes nobody has heard. A stage that wants to know whether its
    input was accepted must compare hashes, and this contract is shaped so that
    comparing hashes is the easy thing to do.

    The truth-layer discipline is unchanged. ``source_audio`` is observed.
    ``provenance`` is copied from the generation manifest and keeps its own
    layers, so the prompt stays labelled as the request it was. ``review`` is a
    human's judgement about fitness and is not a layer at all; see
    :class:`HumanReview`.
    """

    schema_id: Literal["spectral-loom/specimen-review"] = REVIEW_SCHEMA_ID
    schema_version: Literal["0.1.0"] = REVIEW_SCHEMA_VERSION

    specimen_id: SpecimenId
    spec_path: str = Field(min_length=1, max_length=512)
    spec_hash: ContentHash = Field(
        description="Hash of the exact specification bytes the reviewed rendering came from."
    )

    source_audio: SourceAudio = Field(
        description="Observed properties of the exact bytes that were listened to."
    )

    generation_manifest_hash: ContentHash = Field(
        description=(
            "Hash of the generation manifest as it stood when the review was recorded. The "
            "manifest is untracked; this makes it possible to notice that it has since changed."
        )
    )
    cabinet_hash: ContentHash = Field(
        description=(
            "Hash of `model-cabinet.toml` as it stood at review time. The cabinet is the "
            "project's statement of what its model names mean, and re-pinning it changes what "
            "a later regeneration of this specimen would be."
        )
    )

    provenance: list[Provenance] = Field(
        min_length=1,
        description=(
            "The producing stages, copied verbatim from the generation manifest, so the "
            "accepted bytes stay attributable without that manifest being present."
        ),
    )

    review: HumanReview

    @model_validator(mode="after")
    def _check_review(self) -> SpecimenReview:
        stages = [p.stage for p in self.provenance]
        duplicate = {s for s in stages if stages.count(s) > 1}
        if duplicate:
            raise ValueError(f"duplicate provenance stage names: {sorted(duplicate)}")

        ids = [c.id for c in self.review.criteria]
        repeated = {c for c in ids if ids.count(c) > 1}
        if repeated:
            raise ValueError(f"duplicate review criterion ids: {sorted(repeated)}")

        emitted = {h for p in self.provenance for h in p.output_hashes.values()}
        if emitted and self.source_audio.hash not in emitted:
            raise ValueError(
                f"the reviewed audio {self.source_audio.hash} is not among the artifacts this "
                f"document's provenance says were produced ({sorted(emitted)}); a review must "
                f"be about bytes its own record can attribute"
            )
        return self


# ---------------------------------------------------------------------------
# Separation manifest: what a separator was given and what it emitted.
# ---------------------------------------------------------------------------


class AudioArtifact(Contract):
    """One audio file this project wrote, measured after writing it.

    Measured *after*, not before. The numbers here describe the bytes on disk —
    the ones a person will actually hear and a later stage will actually read —
    rather than an in-memory tensor that was quantized on its way out.
    """

    path: str = Field(
        min_length=1,
        max_length=512,
        description="Location relative to the repository root. A claim about where, not what.",
    )
    hash: ContentHash
    duration_s: float = Field(gt=0)
    sample_rate_hz: int = Field(gt=0)
    channels: int = Field(ge=1, le=64)
    peak: float = Field(ge=0, description="Largest absolute sample value, observed.")
    rms: float = Field(ge=0, description="Root mean square over the whole file, observed.")


class Stem(Contract):
    """One output a separator produced, named the way the separator names it.

    ``model_output`` is the single most misreadable field in this project, so it
    is not called ``instrument``. ``bass`` means **HTDemucs assigned this signal
    to its `bass` output**. It does not mean the file contains only bass, and it
    does not mean the source contained a bass.

    The same care applies hardest to ``vocals``. Content appearing there may be
    voice-like source material, model confusion, or leakage from another
    instrument, and a stem that is near-silent is a failure to assign rather than
    proof that nobody sang.
    """

    model_output: Slug = Field(
        description="The separator's own name for this output. Not a verified instrument."
    )
    audio: AudioArtifact
    clipped_samples: int = Field(
        ge=0,
        description=(
            "Samples whose magnitude exceeded full scale and were clamped on write. Recorded "
            "rather than rescaled away: a silent gain change would corrupt every later "
            "comparison against the source."
        ),
    )
    non_finite_samples: int = Field(
        ge=0,
        description="Samples the model emitted that were not finite. Nonzero is a real problem.",
    )


class Diagnostic(Contract):
    """An engineering check, deliberately not an inferred stem.

    A reconstructed mix and a residual are arithmetic performed on the outputs.
    They carry no model opinion, they are not evidence about the music, and
    nothing downstream may treat one as a track. They exist so that a person can
    hear what separation lost, and so that a number for it is on the record
    rather than in somebody's memory.
    """

    id: Slug
    description: str = Field(
        min_length=1, max_length=500, description="What this diagnostic is, in one sentence."
    )
    audio: AudioArtifact | None = Field(
        default=None, description="The rendered diagnostic, where one was written."
    )
    measurements: Extension = Field(
        default_factory=dict, description="Observed numbers. No thresholds, no verdicts."
    )


class Separator(Contract):
    """Exactly which implementation, loading exactly which weights.

    Both halves, because upstream versions them separately: a distribution
    identity alone would not say which bytes were loaded, and a weights revision
    alone would not say which code interpreted them.
    """

    adapter: str = Field(min_length=1, max_length=64, description="This project's adapter name.")

    code_distribution: str = Field(min_length=1, max_length=100)
    code_version: str = Field(min_length=1, max_length=50)
    code_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="Digest the package index published for the exact artifact installed.",
    )
    loaded_with: str = Field(
        min_length=1,
        max_length=200,
        description="Symbol that read the weights off disk, e.g. demucs.hf.load_safetensors_model.",
    )
    applied_with: str = Field(
        min_length=1,
        max_length=200,
        description="Symbol that performed the separation, e.g. demucs.apply.apply_model.",
    )

    weights_repo: str = Field(min_length=1, max_length=200)
    weights_revision: str = Field(
        pattern=r"^[0-9a-f]{40}$",
        description="Immutable upstream revision. Never a branch and never a tag.",
    )
    weights_variant: str = Field(min_length=1, max_length=100)
    model_signatures: list[str] = Field(
        min_length=1,
        description=(
            "Signatures of the models in the bag, as upstream names them. `htdemucs` is a bag "
            "of exactly one model and its signature is part of what produced any stem."
        ),
    )

    model_sample_rate_hz: int = Field(
        gt=0, description="The rate the loaded model works at, read off the model."
    )
    model_audio_channels: int = Field(ge=1, le=64)
    sources: list[str] = Field(
        min_length=1,
        description="The model's own output names, in the order the model emits them.",
    )


class SeparationManifest(Contract):
    """The record that makes one separation auditable and reusable.

    Two jobs, and `docs/provenance.md` says they are the same information: it
    attributes the stems, and it *is* the cache key. Reuse is a comparison of
    this document against a freshly computed key, followed by re-hashing every
    file it claims to describe — because a manifest describing files that have
    since changed is not a cache entry, it is a document making a false claim.

    The truth layers stay apart. Hashes, durations, sample rates, channel counts,
    peaks and residuals are ``observed``: anyone holding the files can recompute
    them. The producing stage is ``inferred``: HTDemucs at an exact revision had
    an opinion about which signal belonged to which of its outputs.

    **No human quality judgement belongs in here.** Whether the bass is actually
    isolated is gate 3, it is answered by ears, and it is recorded in a
    `SpecimenReview`, not in the output of the thing being judged.
    """

    schema_id: Literal["spectral-loom/separation-manifest"] = SEPARATION_SCHEMA_ID
    schema_version: Literal["0.1.0"] = SEPARATION_SCHEMA_VERSION

    specimen_id: SpecimenId
    source_audio: SourceAudio = Field(
        description="The exact bytes that were separated. Observed, and verified before the run."
    )
    source_path: str = Field(min_length=1, max_length=512)

    review_hash: ContentHash = Field(
        description=(
            "Hash of the specimen review that accepted these bytes. Separation does not run on "
            "audio no human has accepted, and this is the receipt for that precondition."
        )
    )
    generation_manifest_hash: ContentHash = Field(
        description="Hash of the generation manifest that attributes the separated bytes."
    )

    separator: Separator
    stems: list[Stem] = Field(min_length=1)
    diagnostics: list[Diagnostic] = Field(default_factory=list)

    cache_key: ContentHash = Field(
        description="Digest over `cache_key_inputs`. A run whose key differs is a different run."
    )
    cache_key_inputs: Extension = Field(
        description=(
            "Everything the key was computed from, so that a stale entry can be diagnosed "
            "rather than merely disbelieved."
        )
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="What the run emitted or had to do, including any explicit fallback.",
    )

    provenance: list[Provenance] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_outputs(self) -> SeparationManifest:
        stages = [p.stage for p in self.provenance]
        duplicate = {s for s in stages if stages.count(s) > 1}
        if duplicate:
            raise ValueError(f"duplicate provenance stage names: {sorted(duplicate)}")

        names = [s.model_output for s in self.stems]
        repeated = {n for n in names if names.count(n) > 1}
        if repeated:
            raise ValueError(f"duplicate stem outputs: {sorted(repeated)}")

        unknown = set(names) - set(self.separator.sources)
        if unknown:
            raise ValueError(
                f"stems {sorted(unknown)} are not among the separator's own outputs "
                f"{self.separator.sources}; a stem must be named by the model that made it"
            )

        ids = [d.id for d in self.diagnostics]
        repeated_ids = {i for i in ids if ids.count(i) > 1}
        if repeated_ids:
            raise ValueError(f"duplicate diagnostic ids: {sorted(repeated_ids)}")

        paths = [s.audio.path for s in self.stems] + [
            d.audio.path for d in self.diagnostics if d.audio is not None
        ]
        collisions = {p for p in paths if paths.count(p) > 1}
        if collisions:
            raise ValueError(f"two artifacts claim the same path: {sorted(collisions)}")
        return self


# ---------------------------------------------------------------------------
# Separation review: what a human decided about one exact separation.
# ---------------------------------------------------------------------------


class ReviewedArtifact(Contract):
    """One file that was actually in the exhibit a reviewer listened to.

    A verdict about "the separation" is worth nothing unless the separation can
    be identified. A directory can be regenerated under a different revision, a
    different backend, or a different parameter and still answer to the same
    name, so the acceptance names **every file by hash**: a later run whose
    bytes differ is a different separation and inherits nothing.

    ``kind`` keeps the same distinction the separation manifest keeps.
    ``model_output`` is an assignment HTDemucs made; ``diagnostic`` is
    arithmetic performed on those assignments and carries no model opinion;
    ``source`` is the evidence they are all claims about.
    """

    name: Slug = Field(description="The artifact's own name, e.g. 'bass' or 'residual'.")
    kind: Literal["source", "model_output", "diagnostic"]
    path: str = Field(
        min_length=1,
        max_length=512,
        description="Where it was when it was reviewed. A claim about where, not what.",
    )
    hash: ContentHash = Field(description="The bytes that were actually heard.")


class SupplementaryListening(Contract):
    """A second opinion that is context, not a reviewer.

    Recorded because leaving it out would misrepresent how the judgement was
    reached, and typed separately from :class:`HumanReview` because a review has
    exactly one author and this is not it. Nothing mechanical reads this field,
    and no downstream stage may treat it as an acceptance.
    """

    listener: str = Field(min_length=1, max_length=200, description="Who, or what, assessed it.")
    nature: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "What kind of assessment this is and how this project came by it, in enough detail "
            "that a reader does not have to assume it was produced the same way the reviewer's "
            "was."
        ),
    )
    summary: str = Field(
        min_length=1, max_length=2000, description="What it said, as reported to this project."
    )


class SeparationReview(Contract):
    """The tracked record that one human judged one exact separation.

    The layer below :class:`SpecimenReview`, and it exists for the same reason.
    ``decision:10`` established that a specimen id names an *intent* and cannot
    stand in for the bytes a person heard. A separation is one step worse: it is
    identified by a directory that will be reused by the next run, so
    `corpus/derived/<specimen>/separation/` can be regenerated on another
    backend, at another revision, or with another parameter and still resolve —
    to stems nobody has heard. This document therefore names the separation
    manifest's own content hash, the separator's exact code and weight identity,
    and every artifact that was in the exhibit, each by hash.

    **The human judgement is still not a truth layer.** "These stems are fit to
    be evidence inputs for activity and onset inference" is a claim about the
    project, not about the recording, exactly as in ``decision:10``. What the
    reviewer perceived in a model output is a fact about their perception of a
    model's assignment, and never a fact about what the source contained: an
    output in which nothing meaningful was heard is a failure to assign, and the
    contract will not let that be written down as an absence in the music.
    """

    schema_id: Literal["spectral-loom/separation-review"] = SEPARATION_REVIEW_SCHEMA_ID
    schema_version: Literal["0.1.0"] = SEPARATION_REVIEW_SCHEMA_VERSION

    specimen_id: SpecimenId
    source_audio: SourceAudio = Field(
        description="The accepted source these stems were separated from. Observed."
    )
    specimen_review_hash: ContentHash = Field(
        description=(
            "Hash of the gate 2 review that accepted the source. A separation of unaccepted "
            "bytes could never have been produced, and this is the receipt for that."
        )
    )

    separation_manifest_path: str = Field(min_length=1, max_length=512)
    separation_manifest_hash: ContentHash = Field(
        description=(
            "Hash of the separation manifest document itself, which is this separation's "
            "identity. A regenerated separation is a different manifest and a different hash, "
            "and it does not inherit this acceptance."
        )
    )
    separation_cache_key: ContentHash = Field(
        description="The manifest's own cache key, copied so the two can be compared later."
    )

    separator: Separator = Field(
        description=(
            "Which implementation loaded which weights, copied verbatim so the reviewed "
            "separation stays attributable from a clean clone where the manifest is absent."
        )
    )

    reviewed_artifacts: list[ReviewedArtifact] = Field(
        min_length=1,
        description="Every file in the exhibit that was listened to, each named by its hash.",
    )

    review: HumanReview
    supplementary: list[SupplementaryListening] = Field(
        default_factory=list,
        description=(
            "Second opinions, recorded as context. `review` has exactly one author and these "
            "are not it; nothing mechanical reads them."
        ),
    )

    @model_validator(mode="after")
    def _check_review(self) -> SeparationReview:
        ids = [c.id for c in self.review.criteria]
        repeated = {c for c in ids if ids.count(c) > 1}
        if repeated:
            raise ValueError(f"duplicate review criterion ids: {sorted(repeated)}")

        names = [(a.kind, a.name) for a in self.reviewed_artifacts]
        collisions = {n for n in names if names.count(n) > 1}
        if collisions:
            raise ValueError(f"two reviewed artifacts share a name: {sorted(collisions)}")

        outputs = {a.name for a in self.reviewed_artifacts if a.kind == "model_output"}
        if not outputs:
            raise ValueError(
                "a separation review must name at least one model output; a review of only "
                "diagnostics is a review of arithmetic, not of a separation"
            )
        missing = set(self.separator.sources) - outputs
        if missing:
            raise ValueError(
                f"the separator emits {self.separator.sources} and this review names only "
                f"{sorted(outputs)}; {sorted(missing)} was not reviewed, and a partial audition "
                f"must not be recorded as a verdict on the separation"
            )
        return self
