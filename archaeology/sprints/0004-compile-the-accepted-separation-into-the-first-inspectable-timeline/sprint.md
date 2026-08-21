---
id: spr_01M0GV19568TPVR34C47C2NPVD
sequence: 4
kind: sprint
status: active
created: 2026-08-20
---

# Compile the accepted separation into the first inspectable timeline

## Goal

Turn the separation Henry has now heard into the first `song.timeline.json` this project has ever
produced, and build the instrument that lets him falsify it with his ears.

The round tells one story and stops in the middle of it:

```text
accepted source bytes
    → accepted separation bytes
    → transparent deterministic signal analysis
    → activity.sample / activity.interval / onset
    → song.timeline.json
    → Timeline Observatory
    → a human can click a claim and hear its evidence
```

Gate 3 of `docs/roadmap.md` becomes durably passed rather than passed-in-a-conversation. Gate 4
gets its compiler, its evidence, and its review surface, and then waits — because gate 4 is not
passed by a document validating, it is passed by a human spot-checking events against audio.

## Rationale

Henry listened to the stems on 2026-08-20 and accepted them as evidence inputs. That verdict
currently exists nowhere a clean clone could find, and the stems it is about are untracked by
policy. The same argument that produced `decision:10` applies one layer down: a specimen id names
an intent, and now a *separation* is identified by a directory too. Regenerate the separation
under a different revision, a different backend, or a different parameter, and
`corpus/derived/<specimen>/separation/` still resolves — to stems nobody has heard. So the gate 3
verdict must be bound to the separation manifest's hash and to every reviewed stem hash, and the
compiler must require *those bytes*, mechanically, before it reads a sample.

The analysis itself is deliberately the least clever thing that could work. Gate 4 admits exactly
three event types, and the point of them is not detection accuracy — it is establishing an
attributable pipeline whose mistakes a human can find. A transparent short-time RMS measurement, an
explicit hysteresis rule over it, and a spectral-flux novelty detector are all things a person can
be shown and can argue with. A model would be a second unexamined opinion stacked on the first.

The trap this round has to avoid is named in advance. `vocals` came back at the separator's noise
floor. An activity method that normalized each stem independently would find that stem's loudest
noise and call it "active", producing a confident timeline claim about a signal that is nothing but
model noise. Absolute level therefore has to stay visible in the rule, not be normalized out of it.

And the whole thing is worth nothing if recompiling produces different bytes. A boundary artifact
that changes when nothing changed cannot be cached, cannot be diffed, and cannot be compared
against a later run — so determinism is designed in rather than hoped for, and run telemetry is
kept outside the semantic document.

## Success criteria

- Gate 3's verdict survives a clean clone: tracked, machine-readable, naming the exact separation
  manifest hash, every reviewed stem hash, the diagnostics that were part of the exhibit, the
  Demucs code and weight identity, the reviewer, the date, and each criterion answer in the wording
  it was asked.
- A separation regenerated to different bytes cannot inherit that acceptance.
- The verdict preserves what was and was not established: `other` is not renamed, no cymbal
  conclusion is drawn from material that was not clearly audible, and "nothing meaningful was
  perceived in `vocals`" is not recorded as "the source contained no vocals".
- The compiler refuses to run unless both reviews match the bytes on disk, and says which hash it
  wanted and which it found.
- Exactly three event types: `activity.sample`, `activity.interval`, `onset`. No notes, beats,
  tempo, sections, instruments, or chords.
- `activity.sample` is `observed`; `activity.interval` and `onset` are `inferred`. No event carries
  a manufactured confidence.
- Every parameter that can change an event is in the provenance and in the cache key.
- The activity rule uses absolute thresholds shared by every track, and the near-silent `vocals`
  output is left unclaimed rather than normalized into activity.
- The timeline's `source_audio` remains the original accepted 48 kHz recording, with events citing
  the 44.1 kHz stem artifacts as evidence.
- Tracks are named for the model output that produced them, never for a guessed instrument.
- Recompiling unchanged inputs is a verified cache hit producing byte-identical bytes and the same
  sha256. Corrupting or removing an input or the declared output invalidates reuse loudly.
- One command opens a loopback-only Timeline Observatory in which an onset marker can be clicked,
  auditioned in a short loop, and A/B'd against the source mix.
- Uncertainty and absence render differently: zero intervals is reported as zero intervals inferred
  under a stated rule, never as absence in the recording.
- The Observatory cannot mutate the timeline, its cache, or its review state.
- The default environment stays light enough to type-check and test without the cabinet, the
  hermetic suite stays hermetic, and nothing audio-shaped or generated becomes tracked.

## Non-goals

- Deciding whether the timeline is any good. Henry is the gate 4 oracle and this round is not
  entitled to an opinion about whether an onset is musically real.
- Basic Pitch, `note` events, pitch, chroma, key, tempo, beat, chord, section, or instrument
  inference. Splitting `other` into guessed instruments is specifically excluded.
- The gate 6 analytical projection and any artistic rendering. The Timeline Observatory is a review
  surface for one gate, not the projection back end.
- Automatic parameter tuning, or replacing the baseline detector with a model. If the baseline
  proves unusable, that is a measurement to record first.
- A second specimen, a changed prompt, or a corpus.
- A generalized review framework. Two review kinds may share the small primitive that already
  exists; they do not justify inventing a third abstraction.
- Pushing commits.
