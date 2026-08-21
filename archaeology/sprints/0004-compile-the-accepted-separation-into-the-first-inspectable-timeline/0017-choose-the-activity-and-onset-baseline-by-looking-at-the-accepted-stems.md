---
id: tsk_01M0GV2ME46CYT9G8E1B8J9GTX
sequence: 17
kind: task
status: closed
sprint: spr_01M0GV19568TPVR34C47C2NPVD
created: 2026-08-20
closed: 2026-08-20
---

# Choose the activity and onset baseline by looking at the accepted stems

## Objective

Decide what `activity.sample`, `activity.interval` and `onset` are going to *mean* by looking at
the accepted stems, before any of it is implemented — and record which parameters were chosen from
evidence and which are arbitrary baselines.

## Acceptance criteria

- The distributions that matter are measured on the accepted stems rather than assumed: per-frame
  level for every model output, and the novelty statistic the onset detector will use.
- The chosen thresholds are shown to sit in a region where the answer barely moves, so they are a
  plateau rather than a fit to one specimen.
- Absolute level stays visible in the rule. No per-stem normalization that would let the loudest
  noise in a near-silent output become "active".
- Every parameter that can change an event is enumerated, with a reason, and marked as evidence-led
  or arbitrary.
- What would justify changing each one later is written down.
- A dragon is opened if touching the data made "activity" less obvious than the roadmap assumes.

## Result

Done, and it changed what got built. Measuring first was not ceremony: the obvious implementation
would have been wrong on this specimen in a way that produced perfectly well-formed events.

### What was measured

Short-time RMS at a 2048-sample window and 1024-sample hop over all four accepted model outputs,
then the spectral-flux novelty statistic the onset detector would use. The full percentile tables
are in `decision:11`. Two facts carried the whole design:

**All four outputs sit on a broadband noise floor near -61 dBFS**, and that floor is the
separator's, not the format's — one least-significant bit of sixteen-bit PCM is about -90 dBFS.

**`vocals` is nothing but that floor.** Its ninety-ninth percentile is -59.3 dBFS and its single
loudest frame in forty-five seconds reaches -54.0. Its largest spectral-flux value in the entire
file is 4.7, against 326, 1397 and 223 for `bass`, `drums` and `other`.

### What that ruled out

Per-track normalization, which is what most implementations of "is this track active" do. Divide
`vocals` by its own peak and its noise floor becomes 0 dB; threshold anywhere sensible and the
timeline acquires confident interval events about a signal Henry heard as silence. The events would
have been indistinguishable from real ones — same type, same schema, same provenance, same evidence
link to a real file — and nothing in the document would have said "this is the loudest noise in an
empty stem". `decision:11` closes that door with the numbers.

### What was chosen, and how arbitrary each part is

**Evidence-led.** The absolute-versus-relative decision, and the rough magnitude of the thresholds.
-50 dBFS to enter is eleven decibels clear of the measured floor and four clear of the loudest frame
in `vocals`; the onset flux floor of 20 is four times `vocals`' largest value and an order of
magnitude below the other three tracks' peaks.

**Arbitrary baselines, and marked as such in the code.** The exact round numbers inside those
ranges. The 100 ms minimum duration and 100 ms merge gap, chosen at the scale of a short musical
note so that a single stray window neither creates an interval nor splits one. The window and hop
sizes, arbitrary within an order of magnitude. The median radius of ±104 ms and peak radius of
±35 ms for onset picking. The 50 ms minimum inter-onset gap.

**The plateau is the argument.** Sweeping the activity pair from (-45, -52) to (-55, -58) moved
inferred coverage by about three percentage points and gave `vocals` zero intervals at every
setting. Sweeping the onset multiplier from 1.5 to 3.0 and the floor from 5 to 20 moved `drums`
between 153 and 180 events and gave `vocals` zero at every setting. A threshold that sits in a
region where the answer barely moves is a threshold that found a gap in the data; a threshold that
had to be placed precisely would have been a fit.

### What would justify changing them

A second specimen at a materially different absolute level, which is the whole calibration question
and is `dragon:4`. A specimen with a genuinely sparse continuous part, which would say whether
`other`'s single 92.8% interval is a property of the arrangement or of the rule. Henry's gate 4
spot-check, which is the cheapest of the three and is available now.

### The dragon this opened

`dragon:4`. The roadmap treats `activity.interval` as obvious and the data says it is not: one rule
produced phrase-like intervals on `bass`, note-decay envelopes on `drums`, a single "the track is
on" interval on `other`, and nothing on `vocals`. One event type is carrying at least three musical
meanings, and the timeline does not distinguish them. The wrong fixes — normalize, tune until
`other` splits, invent a `phrase` type — are named in the dragon so they are not reached for later.

### Also decided here

NumPy moved into the **default** environment rather than the cabinet. `decision:5` keeps *model*
dependencies out of `.venv`; a 15 MB array library that ships no weights is not one, and putting
the transparent half of the pipeline behind an 11 GB optional extra would have made the arithmetic
harder to run than the inference. Its exact version reaches every analysis cache key, because a
different NumPy is a different FFT.
