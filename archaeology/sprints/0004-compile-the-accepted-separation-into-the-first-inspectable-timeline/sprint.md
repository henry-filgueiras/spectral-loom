---
id: spr_01M0GV19568TPVR34C47C2NPVD
sequence: 4
kind: sprint
status: closed
created: 2026-08-20
closed: 2026-08-20
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

## Retrospective (2026-08-20)

Every success criterion met. Five tasks closed, one decision, one dragon opened.
**Gate 3 passes and is now durable. Gate 4 has its compiler, its evidence, its instrument, and no
verdict.**

### What the round changed about what this project believed

**A separation is identified by a directory the next run reuses, and that was load-bearing.**
`decision:10` fixed this one layer up: a specimen id names an intent, so gating on it would have run
on bytes nobody heard. The same hole existed one layer down and was easier to miss, because
`corpus/derived/<specimen>/separation/` looks like a location rather than a name. Re-separate on
another backend, at another revision, or with one parameter changed, and that path still resolves —
to stems nobody has heard, with a gate 3 verdict sitting beside them that appears to be about them.
The fix is the same shape as before: key the review by the *separation manifest's* own content hash,
list every exhibit artifact by hash, and re-hash all of them before recording a word.

**Measuring before implementing changed what got implemented, and it was not close.** The obvious
"is this track active" is per-track normalization, and on this specimen it would have been
catastrophic *invisibly*. All four HTDemucs outputs sit on a broadband noise floor near −61 dBFS,
and `vocals` — which Henry heard as silence — is nothing but that floor. Normalized, its loudest
noise becomes 0 dB and the timeline acquires confident interval events about a signal a human heard
as nothing. The events would have been indistinguishable from real ones: same type, same schema,
same provenance, same evidence link to a real file. `decision:11` closes that door with the numbers.

**The plateau, not the point, is the argument.** Sweeping the activity pair across ten decibels
moved coverage by three percentage points and never gave `vocals` an interval; sweeping the onset
multiplier and floor across a factor of four moved `drums` between 153 and 180 events and never gave
`vocals` one. A threshold that sits where the answer barely moves has found a gap in the data. A
threshold that had to be placed precisely would have been a fit to one specimen, and this project
has exactly one specimen.

**One event type turned out to carry three musical meanings.** `dragon:4`. The roadmap treats
`activity.interval` as obvious; the data produced phrase-like intervals on `bass`, note-decay
envelopes on `drums`, one "the track is on" interval covering 92.8% of `other`, and nothing on
`vocals` — from one rule, unchanged. The name promises more structure than the measurement delivers.
The wrong fixes are written into the dragon so they are not reached for later.

**Determinism had to be designed, and the tests for it had to look for classes rather than
instances.** Comparing two compiles would have caught a wall-clock in the document only by luck:
two runs a millisecond apart can agree on a timestamp. So the tests look for a local path, a
temporary directory, and a clock in a stage that should not have one, by name.

### What exists that did not

A sixth contract, `SeparationReview`, with a generated schema, reusing the `HumanReview` primitive
the contracts already had. Two new modules: `analysis` (the arithmetic, and the argument for every
number in it) and `timeline` (the compiler, its preconditions, its cache, and its canonical bytes),
plus `timeline_observatory`. Three new CLI commands — `accept-separation`, `compile`,
`review-timeline` — all routed. One tracked separation review. **327 hermetic tests, up from 224.**

NumPy moved into the default environment: `decision:5` keeps *model* dependencies out of `.venv`,
and a 15 MB array library that ships no weights is not one. Putting the transparent half of the
pipeline behind an 11 GB optional extra would have made the arithmetic harder to run than the
inference.

4.8 MB of timeline on this machine, untracked. One 40 KB generated page, also untracked.

### Two habits worth keeping

**Prove the guard fires, again.** Nine bytes appended to `vocals.wav` produced a refusal naming both
hashes and exit code 1; one byte appended to the timeline produced a named cache miss and a
recompile back to the same sha256; editing the separation manifest after the review made the gate 3
verdict stop resolving. Same discipline as sprint 3's negative control, applied to three new guards.

**Drive the browser, not only the tests.** The Timeline Observatory's canvases all needed an
explicit CSS height — without one, a canvas with `width: 100%` scales to preserve its attribute
aspect ratio, and a 76-pixel lane became six hundred pixels tall on a wide window, pushing the lanes
below it off the screen. Every Python test passed. The bug defeated the entire point of the page,
and nothing short of looking at it would have found it.

### What is unmeasured, stated so a later round does not mistake it for settled

- **The timeline.** Nobody has checked an event against the audio. 153 onsets on `drums` is 153
  hypotheses from one detector at one parameter set, and whether any of them lands on something
  audible is exactly the open question.
- **Everything stops around 40 s** in a 45.00 s file — last onset 39.97 s on `drums` and `bass`,
  39.52 s on `other`, and `other`'s single interval ends at 41.77 s. Five seconds carry no inference
  from any track. Tail, fade, or the piece ending: unknown.
- **The median inter-onset gap is 0.30–0.33 s on all three claimed tracks**, and the specification
  *requested* 96 BPM, at which an eighth note is 0.3125 s. Nothing here measured a tempo. The
  request is `requested` and stays there, and a detector whose median gap resembles a subdivision is
  not evidence that the subdivision exists.
- **The thresholds are calibrated on one recording's absolute level.** A mix mastered thirty
  decibels quieter would produce an empty timeline and fail silently. `dragon:4`.
- **The onset detector cannot report an onset at t = 0**; the first frame has no predecessor and its
  flux is zero by definition.
- **CI has still never run**, Linux is still unexercised, and CPU separation has still never run.

### Next

Henry listens. `./loom review-timeline sparse-funk-exposed-bass`, then `1`–`4`, `N`, `enter`, `S`.
The questions are printed beside the URL. **Gate 4 is not passed by this document validating**, and
nothing downstream — no Basic Pitch, no `note` events, no projection, no second specimen — starts
before he answers.
