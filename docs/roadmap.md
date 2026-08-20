# Roadmap

Not a feature backlog. A ladder of **evidence gates**: each rung states what must be true before
the next is attempted, and each is small enough that failing it is informative.

The reason for this shape is that everything after gate 1 is expensive and slow to judge —
multi-gigabyte downloads, long runs, and outputs whose quality can only be assessed by listening.
A backlog would let all of that proceed in parallel and produce a large amount of work that nobody
can attribute to an input. A ladder makes each expensive step justify itself first.

## Gate 0 — Repository and contracts ✅

Done. Contracts, generated schemas, infrastructure CLI, artifact policy, CI, documentation, and
the founding archaeology. No model, no audio, no inference, no pixels.

**Evidence:** `uv sync --locked` reproduces the environment; lint, types, tests, and the schema
drift check pass; the example specification validates; a synthesized timeline validates;
malformed documents fail with errors that name the offending field.

## Gate 1 — Pinned model bootstrap ✅

Done. `model-cabinet.toml` pins all three, and the unit of pinning turned out not to be "a model
revision": upstream versions code and weights separately, so each entry records the implementation
that executes, the assets it loads, and the runtime whose version changes results.

**Evidence:** all three co-exist in one Python 3.11 environment on Apple silicon — the expectation
in `archaeology/decisions/0005` was wrong and `archaeology/dragons/0002` is closed against
measurement. `scripts/bootstrap_cabinet.py` satisfies the `scripts/README.md` contract, and its
second run verified 11.1 GB against upstream sha256 and downloaded nothing with every outbound
socket raising. `scripts/smoke_cabinet.py` ran each entry once: Basic Pitch on the CoreML
`.mlpackage`, Demucs and ACE-Step on MPS.

## Gate 2 — One specimen, accepted by ear ⏳

Generate a single 30–60 second instrumental specimen from `corpus/specs/example.yaml` with a
resolved revision. Listen to it. Accept or reject it as a human.

**Where it stands:** one candidate exists for `sparse-funk-exposed-bass` — 45.00 s, 48 kHz stereo,
generated on MPS from the pinned turbo checkpoint, byte-reproducible across runs. **Nobody has
heard it.** The gate is not passed by generating; it is passed by a human listening.

**Passes when:** one specimen exists, has been listened to, and has been accepted — with the
acceptance recorded, including what was wrong with any rejected attempts. **No corpus is generated
before this gate passes.**

## Gate 3 — Separation, inspected

Separate the accepted specimen with Demucs. Listen to the stems.

**Passes when:** the stems have been heard, and the record says whether the bass is actually
isolated or whether the separation smeared it — because every later inference reads these files,
and an unheard stem is an unexamined assumption.

## Gate 4 — A minimal timeline

Compile a `song.timeline.json` from stem activity and onsets. Only `activity.sample`,
`activity.interval`, and `onset`. Full provenance on every stage.

**Passes when:** the timeline validates, its events are spot-checked against the audio by a human,
and re-running the compiler on unchanged inputs hits cache and produces a byte-identical document.

## Gate 5 — Note inference, optional

Add Basic Pitch. Notes are an **additional** event type, never a required one: a timeline without
notes stays valid, and a stage that fails degrades the timeline rather than failing the compile.

**Passes when:** notes appear for the bass stem, carry confidences, and the pipeline still
produces a usable timeline with note inference switched off.

## Gate 6 — Analytical projection

Render a debug projection: tracks, events, confidences, and provenance, synchronized to the audio.
Its job is to make an inference inspectable, and it is the tool that will judge every later gate.

**Passes when:** a wrong inference is visible in it without reading JSON, and uncertainty renders
differently from absence.

## Gate 7 — Artistic projection

Render a multilayer artistic projection from the same timeline, sharing no code path with the
analytical one beyond the timeline reader.

**Passes when:** both projections render the same specimen from the same file, and neither has
written to it.

## Gate 8 — Oracle comparison

Compare inferred results against a corpus with ground truth, such as Slakh2100, which ships
aligned MIDI alongside rendered stems.

**Passes when:** onset and note inference have a measured error against ground truth, reported
per stem, with the failure modes named rather than averaged away.

## Explicitly deferred

Not "later" as a soft no — these are out of scope for the foreseeable project, and a change of
mind about any of them is a decision that belongs in `archaeology/decisions/`.

- **Live streaming** of any kind.
- **Spotify integration, and streaming-service capture in general.** Spectral Loom works on audio
  it generated from a specification it holds, or on audio a user supplies deliberately. There is
  no ingestion path from a streaming service and none is planned.
- **Remote inference.** Everything runs locally; a model that cannot run on the host is a model
  this project does not use yet.
- **Accurate engraved sheet music.** Engraving needs a musical ontology this project has not
  earned, and `archaeology/dragons/0001` is open about how little of that ontology is settled.
- **Generalized DAW functionality.** Not an editor.
- **A large UI.** The projections are the interface.
- **Cloud infrastructure.**
- **Mass corpus generation** before a single specimen has passed gates 2 and 3. Generating a
  thousand songs before hearing one is how a project ends up with a thousand unusable songs.
