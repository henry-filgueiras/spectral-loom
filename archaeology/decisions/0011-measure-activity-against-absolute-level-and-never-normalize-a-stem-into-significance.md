---
id: dec_01M0GW9891RE1DY1NQ2X479M2M
sequence: 11
kind: decision
status: accepted
created: 2026-08-20
---

# Measure activity against absolute level, and never normalize a stem into significance

## Context

Gate 4 asks for three event types, and two of them turn on the word "active". Something has to
decide, for each model output, when that output is doing something and when it is not.

The obvious implementation is per-track normalization: divide each track by its own peak, threshold
the result at some fraction, done. It is what most tutorials do, it is scale-free, and it means one
threshold works for a loud drum stem and a quiet bass stem alike.

On this project's first specimen it would have been catastrophic, and — this is the part worth
recording — **it would have been catastrophic invisibly**.

Measuring the accepted separation before writing any of it gave the reason. Short-time RMS at a
2048-sample window and 1024-sample hop, over all four HTDemucs outputs:

| output | p10 | p50 | p90 | max |
| --- | --- | --- | --- | --- |
| `drums` | -60.9 | -47.7 | -16.3 | -11.8 |
| `bass` | -61.4 | -25.5 | -20.6 | -16.1 |
| `other` | -39.5 | -28.4 | -23.5 | -19.4 |
| `vocals` | -61.5 | -61.2 | -61.0 | **-54.0** |

All four sit on a broadband floor near -61 dBFS. That is not sixteen-bit quantization — one
least-significant bit is about -90 dBFS — it is the separator's own output noise. And `vocals`,
which Henry auditioned at gate 3 and described as perceptually silent, is *nothing but that floor*:
its ninety-ninth percentile is -59.3 dBFS and its single loudest frame reaches -54.0.

Normalize that track by its own peak and its noise floor becomes 0 dB. Threshold anywhere sensible
and the timeline acquires confident `activity.interval` events about a signal a human heard as
silence. The events would have looked exactly like real ones: same type, same schema, same
provenance, same evidence link to a real file. Nothing in the document would have said "this is the
loudest noise in an empty stem".

The same pressure exists in the onset detector. A purely adaptive threshold — flux against its own
local median — is also scale-free, and on a track containing only noise it will happily find the
biggest noise.

## Decision

**Every level threshold in `spectral_loom.analysis` is absolute, in dBFS against full scale, and
shared by every track. No analysis normalizes a stem by its own peak, its own mean, or any other
per-track statistic.**

Concretely:

1. `activity.interval` uses a hysteresis pair of **-50 dBFS to enter and -56 dBFS to leave**, the
   same two numbers for every track. The exit threshold cannot start an interval on its own — that
   is what makes the pair hysteresis rather than two thresholds — so a track that never reaches
   -50 dBFS is never active however close to -56 it hovers.

2. `onset` thresholds `flux >= median_multiplier * local_median + flux_floor`. The multiplier is
   relative and adapts to how busy the track is; **the floor is absolute**, in the same
   summed-magnitude units the flux is measured in, because every stem is in the same amplitude
   units. That floor is the level gate, and a second one in dBFS would say the same thing twice.

3. Where a level appears in an event payload it is in dBFS, not a normalized fraction, so a reader
   can see how loud the evidence actually was.

4. The dB scale has a **floor at -120 dBFS** rather than reaching negative infinity, so digital
   silence has a number a document can carry. It is thirty decibels below one bit of sixteen-bit
   PCM and cannot act as a threshold by accident.

### Why these numbers, and how arbitrary they are

-50 dBFS is eleven decibels clear of the measured noise floor and four clear of the loudest frame
in `vocals`. -56 dBFS is five decibels clear of the floor and lets a note decay finish without the
interval chattering. Both are round numbers picked inside a range, not fitted values.

The range matters more than the point. Sweeping the pair from (-45, -52) to (-55, -58) moved
inferred coverage by about three percentage points on `bass`, `drums` and `other`, and gave `vocals`
zero intervals at every setting. The onset floor behaves the same way: from 5 to 20, with the
multiplier from 1.5 to 3.0, `drums` moved between 153 and 180 events and `vocals` stayed at zero,
because its largest flux value in the entire file is 4.7 against `bass`, `drums` and `other` at 326,
1397 and 223. **These thresholds sit on a plateau, which is the only honest reason to believe them
on one specimen.**

## Consequences

A stem quieter than -50 dBFS throughout produces no `activity.interval` events at all. That is the
intended behaviour and it is also the thing most likely to be misread, so two things follow.

**Absence must render as absence of inference.** Zero intervals is "zero intervals inferred under
this rule and these thresholds", never "the recording is silent here". The compiler's report says
so in those words and the Timeline Observatory has to as well; this is `principle:1` applied to a
number instead of to a label.

**A genuinely quiet piece of music would be missed.** A mix mastered thirty decibels below this one
would produce a timeline with no activity in it, and the failure would be silent. That is a real
cost of absolute thresholds and it is accepted for now, because the alternative failure — inventing
events in an empty stem — is worse and harder to notice. What would change this decision is a
second specimen at a materially different level, which is `dragon:4`.

The thresholds are in the cache key and in the provenance of every stage that used them, so changing
one is a cache invalidation with a diff, not a silent reinterpretation of documents already written.

### What was rejected, and why

**Per-track peak normalization.** The whole subject of this decision. It makes every stem look
equally significant, which is exactly the claim the evidence does not support.

**Per-track normalization with an absolute floor as a guard.** Better, and still wrong in the same
direction: it makes the *shape* of the rule depend on the track's own loudest moment, so the same
audio in a quieter mix would be thresholded differently for reasons that have nothing to do with
what a person hears.

**A relative threshold against the source mix's level.** Tempting, since the mix is the shared
reference. Rejected because the mix is the sum of four outputs and its level therefore depends on
how the separator distributed energy — which is the thing being measured, not a fixed reference to
measure it against.

**Adaptive-only onset thresholding.** Standard, and it is what the relative half of the rule
already does. Rejected as the whole rule because a purely adaptive threshold has no notion of "too
quiet to matter", which is precisely the case `vocals` presents.
