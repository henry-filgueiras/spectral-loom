# Architecture

Spectral Loom is a compiler. It has a source of truth, a typed intermediate representation, and
back ends that may differ in style but not in meaning.

```text
music generator
    → song audio          (1) source / specification, then audio
    → source separation
    → stem-specific analysis
    → song.timeline.json  (3) inferred semantic timeline
    → visual projections  (4) back ends
```

The first arrow is implemented: a `SongSpec` becomes generated audio and a manifest that makes it
attributable. Nothing after it exists — no separation, no timeline, no projection. This document
describes the shape the rest must take and the invariants none of it may violate.

## The four layers

### 1. Source and specification

A `SongSpec` is a request: a stable specimen id, a generator adapter and model identity with an
exact revision, a natural-language prompt, a seed, a requested duration, and optional requested
BPM, key, time signature, and instruments. It is authored before any audio exists.

A specification is **not evidence about a recording**. It says what was asked for. The generator
may return a different tempo, a drifted key, and none of the requested instruments. Every musical
field is named `requested_*` so that this is visible at the point of use rather than remembered.

Specifications are tracked in Git. They are small, textual, human-authored, and they are the
input that makes a specimen reproducible when combined with a pinned model revision.

### 2. Generated or supplied audio

Audio is the **evidence-bearing source**. Everything downstream is a claim about it, and any
claim can be re-checked by anyone holding the file.

Audio is not tracked in Git: it is bulky, and it is regenerable from a pinned specification plus
a pinned model revision. It is identified by content hash, and that hash appears in the provenance
of every stage that consumed it.

Audio may also be supplied rather than generated. The pipeline does not care which, as long as
the hash is recorded. **Audio is never captured from a streaming service** — see the deferral list
in [roadmap.md](roadmap.md).

### 3. Inferred semantic timeline

Separation and analysis produce a `song.timeline.json`: an envelope carrying a schema id and
version, the specimen id, the source audio hash and duration, an explicit time unit, the
provenance of every producing stage, logical tracks, and generic timed events.

An event has a namespaced type, a start, an optional end, an optional confidence, an evidence
reference, and a namespaced payload. The vocabulary is open on purpose. Early event types are
expected to be `activity.sample`, `activity.interval`, and `onset`; notes arrive later, and only
after a real stem has been inspected. Chords, sections, lyrics, and engraving are not modelled.

This layer is expensive to produce and is cached. It is untracked.

### 4. Visual projections

A projection reads a timeline and draws. Two are planned — an analytical/debug projection whose
job is to make an inference inspectable, and an artistic multilayer projection whose job is to be
worth watching — and they are the same program with different back ends, not two pipelines.

Projections are cheap to redo and are untracked.

## Invariants

These are the rules that make the pipeline auditable. A change that violates one of them is an
architectural change and belongs in `archaeology/decisions/`.

**Audio remains the evidence-bearing source.** Not the prompt, not the timeline, not a cached
analysis. When two of them disagree, the audio is right by definition and the other is a claim
that failed.

**A positive inference links to its source interval.** Every event carries an `evidence`
reference naming the artifact it came from and the stage that read it, and the event's own
start and end are the interval within that artifact. An observation that cannot be traced back to
an interval of audio is an assertion, and the contract has no room for one.

**A negative inference does not prove absence.** No guitar events in a track means the analyser
did not detect a guitar. It does not mean there is no guitar. This distinction has to survive into
the projections: "we found nothing here" and "there is nothing here" must not render identically,
and a projection that draws silence where it means uncertainty is lying about the evidence.

**Expensive inference is cached independently from cheap rerendering.** Changing a colour must
never re-run Demucs. Separation, analysis, and rendering are separate cache domains, and the
renderer's inputs are a timeline file plus its own parameters.

**Every cache key includes input hashes, model revision, and relevant parameters.** A cache entry
whose key cannot be recomputed from the artifacts it claims to describe is garbage, not a cache.
The provenance record and the cache key are the same information, which is why they are the same
structure.

**Visual projections cannot silently mutate semantic observations.** A projection reads the
timeline. It never writes it. If a projection needs a derived value, that value is either
computed in the projection and stays there, or it is promoted to a real analysis stage with its
own provenance entry. A human correction is also not a mutation: it is a new stage with
`truth_layer: corrected`, recorded alongside the inference it overrides rather than erasing it.

**The renderer communicates through versioned files, not Python imports.** The rendering half of
this project may well end up in another language. It reads `song.timeline.json` and the schema
that describes it. It does not import Python internals, and no Python type is part of the
contract between the halves.

## Truth layers

Four, and they never collapse:

| layer | meaning | example |
| --- | --- | --- |
| `requested` | authored before the audio existed | prompt, seed, requested BPM |
| `observed` | measurable by anyone holding the artifact | duration, hash, sample rate |
| `inferred` | a named model's opinion at an exact revision | onsets, stem activity, notes |
| `corrected` | a human override, recorded as its own stage | a fixed downbeat |

Every provenance entry names its layer. See `archaeology/principles/0001`.

## Cross-language and cross-environment stages

ACE-Step, Demucs, and Basic Pitch **do** resolve into one Python 3.11 environment on Apple
silicon. That was measured rather than predicted, and it contradicts what
`archaeology/decisions/0005` expected; `archaeology/dragons/0002` is closed with the evidence. The
cabinet is therefore one optional dependency group materialized into `.venv-cabinet/`, and the
generation stage runs in-process rather than across a subprocess boundary.

The hedge stays, because it is free and the situation is not permanent: stages communicate through
hashed files, so a stage may still run in a separately managed pinned environment, or in another
language, invoked as a subprocess. A stage that does so still writes the same provenance envelope
and names the environment it actually used. The next model added to the cabinet is the one that
may cost this, and nothing above has to change when it does.

## What this architecture deliberately does not have

No plugin system, no event bus, no abstract base class with one implementation, and no renderer
interface with no renderer behind it. The seams that exist — the timeline file, the provenance
envelope, the cache key — are the ones the pipeline cannot work without. Everything else waits
until a second real case exists to generalize from.
