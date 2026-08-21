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

## Gate 2 — One specimen, accepted by ear ✅

Done. Henry listened to the whole file on 2026-08-20 and accepted it, on the first candidate, with
no rejected attempts.

**Evidence:** `corpus/reviews/sparse-funk-exposed-bass.8ff73623a29d.review.json`, tracked, naming
the exact accepted bytes — `sha256:8ff73623…9aa628`, 45.00 s, 48 kHz, stereo — the reviewer, the
date, and all four criterion answers. Bass audible and exposed: yes. Useful silence between
phrases: yes, with the drums continuous and the other instruments leaving arrangement space. Parts
separable by ear: yes. Vocal bleed or another obvious generator failure: none perceived.

What was accepted is narrow and the receipt says so: **these exact bytes are suitable as this
project's first experimental specimen.** Nothing about the requested tempo, key, or instruments was
established — nobody has analysed the audio, and a listener's ear is not a measurement. See
`archaeology/decisions/0010` for why the acceptance is keyed by hash rather than by specimen id,
and why a human judgement is not one of the four truth layers.

## Gate 3 — Separation, inspected ✅

Done. Henry auditioned every model output and the diagnostics in the Stem Observatory on
2026-08-20 and accepted the separation as evidence input.

**Evidence:** `corpus/reviews/sparse-funk-exposed-bass.3ccd7df63e7f.separation-review.json`,
tracked, naming the separation manifest's own content hash — `sha256:3ccd7df63e7f…b449cf3f` — the
pinned Demucs code and weight identity, and all seven artifacts that were in the exhibit, each by
hash. The bass is clearly isolated with very little leakage; a possible slight kick-drum leak was
heard but was subtle enough to be a muted bass note, so it is recorded as `unclear` rather than
resolved by guessing. Kick, snare/rimshot and hi-hat material is coherent, with no melodic leakage
and no damaged transients. `other` is **not** a single-instrument stem — several musical and
timbral voices remain lumped together — and it is therefore not renamed. `vocals` is perceptually
silent. The reconstruction retains the source's character with no objectionable artifacts, and was
perceived as somewhat lower in overall level, which is preserved as the perceptual observation it
is rather than replaced by a signal metric.

Two answers are careful on purpose, and the record says why. **No cymbal verdict is drawn**: the
accepted source offered no clearly audible cymbal or crash material to draw one from, so
"insufficient material to judge" is what is written down, not "the separator lost the cymbals".
And a perceptually silent `vocals` output is **a failure to assign**, never evidence that nobody
sang.

## Gate 4 — A minimal timeline ✅

Done. Henry spot-checked the compiled timeline against the audio on 2026-08-21, over two days, and
accepted it with its limitations recorded rather than resolved.

**Evidence:** `corpus/reviews/sparse-funk-exposed-bass.47e0178cc5b9.timeline-review.json`, tracked,
bound to the document's own sha256 so a recompilation under any changed parameter cannot inherit the
verdict, and carrying the gate 3 and gate 2 receipts it stands on. The timeline validates, recompiles
byte-identically — `sha256:47e0178c…c977c4`, confirmed by a forced recompile and a verified cache hit
— and its 8169 events across four model outputs have been heard.

**What passing means is narrow, and the receipt says so:** this document is usable and attributable,
and its mistakes are findable by a person. It is **not** accurate, and the eighteen findings in
`archaeology/logs/0002` say exactly how it is not.

The detector's precision is good on both tracks examined closely: **one false positive in 95 `bass`
onsets** — and the reviewer found the only one — and one flagged event in 153 on `drums`. Essentially
every failure is a **recall** failure on quiet or dense material, and they all arise from one
mechanism: *the adaptive term reads a busy neighbourhood as evidence that nothing in it is
exceptional.* The clearest instance is a dense flourish after 39.5 s containing 19 novelty peaks and
zero accepted onsets, at a level louder than the track's own median.

Three things this gate established that were not known before it:

- **`activity.interval` is the weakest part of the vocabulary and should not be built on.** Its count
  on `bass` and `drums` is determined by where the 100 ms merge threshold falls in a continuous
  distribution of gaps, with no plateau anywhere. See `archaeology/dragons/0004`.
- **Cross-stem leakage is real and was confirmed by measurement**, not by coincidence: at 12.190 s the
  `bass` and `drums` stems correlate at 0.969 below 300 Hz against a median of 0.092 elsewhere. Which
  instrument the shared signal belongs to cannot be established from the stems, because both stems
  are the separator's opinion. This is a *correct analysis of incorrect evidence* — a third failure
  mode that no threshold fixes.
- **The gate was passed by the instrument being good enough to argue with**, not by the detector
  being right. The Timeline Observatory needed twelve rounds of change during the review, and two of
  its bugs were findable only by opening a browser with the whole Python suite green.

## Gate 5 — Note inference, optional
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
