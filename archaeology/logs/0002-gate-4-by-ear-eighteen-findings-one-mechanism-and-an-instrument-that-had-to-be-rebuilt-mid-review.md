---
id: log_01M0K5VR378QYXR4XDTD84XGME
sequence: 2
kind: log
created: 2026-08-21
---

# Gate 4 by ear: eighteen findings, one mechanism, and an instrument that had to be rebuilt mid-review

## What the review actually was

Henry spot-checked the first `song.timeline.json` this project has ever produced —
`sha256:47e0178c…c977c4`, 8169 events across four HTDemucs outputs — against the audio, by ear, in
the Timeline Observatory. It took most of two days, produced eighteen findings, and required twelve
rounds of changes to the instrument *during* the review, because most of what he needed to see was
not visible until he tried to see it.

**Gate 4 passed.** The verdict and every criterion answer are in
`corpus/reviews/sparse-funk-exposed-bass.47e0178cc5b9.timeline-review.json`. What follows is the
evidence behind it, kept because a verdict without its reasons is worth very little six months later.

## The single mechanism behind almost every failure

Eighteen findings collapse to one sentence: **the adaptive term reads a busy neighbourhood as
evidence that nothing in it is exceptional.**

The onset rule is `flux >= 2.0 x local_median + 20`. The local median answers *how much is happening
here*, and the rule uses that as a proxy for *how much should be happening for something to count*.
Those are different questions, and this material makes them diverge — in both directions.

- **Busy neighbourhood, high median, high bar.** Bass hammer-ons at 2.833, 12.539 and five more; a
  pitch shift down at 15.093 on `other`; a quiet re-articulation after a loud one. All real, all
  declined.
- **Steady sustain, collapsed median, low bar.** The one false positive in 95 bass onsets, at
  26.842: a 12% wobble in the low band of a sustaining note, admitted because the note's own
  steadiness had dropped the local median to 5.73 against a track median of 7.28.
- **The strongest instance is the tail.** After 39.5 s `other` carries a dense multi-voice flourish
  — 108 frames above -50 dBFS, peaking at -21.2 dBFS, louder than its own median for the whole
  piece — containing **19 novelty peaks above flux 8, of which zero were accepted.** Their
  thresholds run 110 to 148, implying local medians three to four times the track's typical value.
  A passage can be loud, busy and eventful and produce nothing at all, not because it is quiet but
  because it is *uniformly* eventful.

Henry's own summary, arrived at independently and in musical language: the detector *"can pick up on
the things that are clearly plucked or enunciated, but can miss nuanced/quick fills/licks/runs, or
when multiple voices share the stage."* Multiple voices sharing the stage **is** an elevated local
median.

## Precision is good; recall is where the failures are

This was not the picture the first few findings suggested, and it matters.

Classifying all 95 accepted `bass` onsets by two crude proxies — did the dominant low bin move, did
the short-time level rise:

```
  pitch moved:                        61
  level rose >= 1 dB, pitch steady:   32
  NEITHER:                             1     <- the only one Henry flagged
```

Robust across thresholds: 1 of 95 at a 0.5 or 1 dB criterion, 2 at 2 dB, 4 at 3 dB. On `drums`,
one flagged event in 153 accepted onsets across a continuous 45-second drum part.

So the detector is **conservative and mostly right about what it claims**, and wrong mostly about
what it declines. Those call for different responses and only one of them is urgent.

## The two dials bind on different populations, and one specimen cannot separate them

Henry spent most of the review moving the absolute floor, because for a long time it was the only
dial. It turned out to reach only part of what he was looking for.

- **Floor binds, multiplier fine.** Seven bass hammer-ons, needing floors from 1.08 to 16.87 — a 16x
  spread, with no single value catching all of them. Floor 14 caught four, which is exactly what he
  observed. Reaching the last needs floor 1.08, at which `vocals` acquires 30 onsets of pure noise.
- **Floor cannot reach them at all.** Twenty-five cymbal-shaped declined peaks on `drums` where the
  adaptive term alone already exceeds the flux, so no floor at any value including zero admits them.
  The hi-hat ghost note at 19.841 is one: 88.5% of its rise above 4 kHz, needing multiplier 1.94
  against a compiled 2.0. It misses by three percent of the dial nobody was moving.
- **Neither reaches them.** Ten band-limited slow swells on `other`, three unclaimed, the largest
  rising 23.8 dB over 279 ms — about 1 dB per frame, where spectral flux only ever compares one
  frame to the next. `17.682` has flux 13.62 against a threshold of 56.18. No setting of either dial
  reaches a gradual rise; it is a third thing the rule cannot express.

And with both dials movable, a region appears that no single-parameter sweep could see:

```
                       drums  bass  vocals   admits the ghost note
  floor 20, mult 2.0     153    95       0   no        <- compiled
  floor 10, mult 1.0     164   153       0   yes
  floor  0, mult 1.9     224   202     144   yes       <- vocals breaks
```

The floor must stay above roughly 5 or the near-silent output fills with noise whatever the
multiplier does — but with the floor merely held there, the multiplier can fall a long way.

## Three things the rule does that nobody intended

**It is not monotonic.** Relaxing the multiplier from 1.1 to 1.0 on `other` *removed* an event: the
earlier peak at 9.671 finally cleared, and 9.718 is 47 ms later, inside the 50 ms minimum gap, so it
was rejected in favour of the peak that now preceded it. The detection moved rather than
multiplying. Every "lowering the floor gains N events" in this review was a safe shorthand only
because the gap rule never fired at the compiled values.

**The gap rule is greedy by time, not by strength.** It walks peaks in order and rejects anything
within 50 ms of the last *accepted* one, so a weaker earlier peak can suppress a stronger later one.

**The `activity.interval` count is the merge threshold, not the music.** Every gap between
consecutive intervals on `bass` and `drums` falls between 0.116 and 0.209 s. At a merge gap of
0.21 s both tracks collapse to a single interval; the count falls monotonically from 65 to 1 with
**no plateau anywhere**, unlike the dBFS thresholds `decision:11` rests on. Worse, the observed
0.116 s minimum is an artifact of the threshold itself: with a 23.22 ms hop, the smallest gap
surviving a 0.10 s merge is five hops. The distribution is truncated from below *by the rule*, and
what remains is a continuum sliced at an arbitrary point.

## Confirmed cross-stem leakage, and a third kind of failure

At **12.190 s** the `bass` and `drums` stems correlate at **+0.969 below 300 Hz**, against a median
of 0.092 and a maximum of 0.659 across every other accepted bass onset. Two instruments playing
together produce uncorrelated waveforms; a shared signal does not. This is one signal the separator
put in two places, and the stems track each other's low-band energy within a constant 9-10 dB for
70 ms with an identical dominant-frequency trajectory before parting completely.

**Which instrument it belongs to cannot be established**, and that is not a gap in the measurement.
Decay does not discriminate (35 ms, the same as the hardest pluck in the file). Spectral flatness
does not discriminate. The source cannot arbitrate because the source is everything at once — which
is the entire reason a separator exists. This is precisely the ambiguity Henry recorded at gate 3 as
`unclear`: *"a possible slight kick-drum leak was heard, subtle enough that it could equally be a
muted bass note; the reviewer could not tell which."* The instruments cannot tell either.

A second case at **7.210 s** is suggestive and unproven: waveform correlation only +0.182, but
`other`'s content sits 2.90x more on the bass note's harmonic series than between it — a different
mechanism, one note split across two stems by partial rather than copied as a waveform. It stays
unproven because 344.5 Hz is a partial `other` carries elsewhere in the piece anyway.

**This is a third failure mode and it is not like the other two.** The onset at 12.190 is a *correct
analysis of incorrect evidence*: the detector did the right thing with the stem it was given, and the
stem may hold something belonging to the drums. `docs/architecture.md` already says a stem is "a
model's opinion rather than a measurement"; this is the first time that produced a consequence in a
timeline. The event is a true positive with respect to `bass.wav` and possibly a false positive with
respect to the music, and **nothing in the timeline can distinguish those readings** — the evidence
link points at the stem, which is exactly as far as its warrant extends. No threshold fixes it.

## A hypothesis that died

15.093 on `other` is a pitch shift *down*, and since spectral flux is half-wave rectified, downward
shifts looked like they should produce systematically less novelty — a structural blind spot rather
than a threshold. Tested across every dominant-partial step of at least 80 cents: `other` up 18.91
vs down 19.38 median flux, `bass` up 0.41 vs down 0.66, and the small acceptance differences run in
**opposite directions** on the two tracks. A pitch change moves every harmonic, so moving down still
creates energy where there was none. The prediction failed, and its failure tidies the story rather
than complicating it.

## What the instrument had to become

The Observatory was built before the review and was not sufficient for it. Twelve rounds of change
during the review, each prompted by a specific thing Henry could not see or do:

- **Declined peaks** drawn, clickable and auditionable — because the first finding needed a Python
  shell to reach its numbers.
- **A click track** sonifying every marker at its own pitch — *"I'm not good enough at linking the
  visual to the sound cue"* is not a skill gap, it is the wrong sense being asked to do the work.
  Two candidates 82 ms apart are six pixels at full-file zoom. Sonifying detections is how onset
  detection has been evaluated for as long as it has existed, and its absence from the first version
  was an oversight rather than a scoping decision.
- **Hypothetical floor and multiplier**, deriving from what the compiler already computed and
  checking themselves against it on every track.
- **All four outputs on one axis**, because *"is kick leakage causing false bass onsets"* was a
  printed review question the page could not answer.
- **Marks with notes**, because batching observations only worked while every row meant the same
  thing.
- Plus: audible interval edges, follow-the-playhead, drag-to-select, a loop-fit zoom detent, marks
  drawn across the lanes, and focus handed back by controls that were swallowing the space bar.

Two bugs in it were found only by opening a browser, with the entire Python suite green: a page that
never executed because a `\n` written in JavaScript was consumed by Python's own string parser, and
canvases six hundred pixels tall because `width: 100%` with no CSS height preserves an attribute
aspect ratio. Both are recorded where they happened.

## What is still unmeasured

- **One specimen, 45 seconds, one genre, one separator, one backend.** Every number here.
- **Whether the extra events a relaxed rule admits are real.** Floor 10 with multiplier 1.0 takes
  `bass` from 95 to 153. Nobody has listened to those 58.
- **What `activity.interval` should mean.** `dragon:4`, now considerably better evidenced and no
  closer to resolved.
- **The direction of the 12.190 leakage**, and whether `other` at 7.210 is leakage at all.
- **Drum sound categories.** Henry wants cymbal, toms, hi-hat and bass drum distinguished; nothing
  in this project distinguishes them and nothing here is a step toward it.
- **CI has still never run. Linux is still unexercised. CPU separation has still never run.**
