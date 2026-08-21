---
id: tsk_01M0GV2MEQ38AR91HZ6JR5H9T6
sequence: 19
kind: task
status: closed
sprint: spr_01M0GV19568TPVR34C47C2NPVD
created: 2026-08-20
closed: 2026-08-20
---

# Compile the accepted separation and measure what came out

## Objective

Run the compiler on the exact accepted separation, and report what came out descriptively without
grading it.

## Acceptance criteria

- The timeline validates against its contract.
- Per model output: `activity.sample` count, `activity.interval` count and total duration, the
  fraction of the timeline they cover, `onset` count, and the measured level and novelty
  distributions.
- Nothing in the report converts an event count into a musical claim. Thirty-eight onsets is
  thirty-eight hypotheses from one detector at one parameter set.
- A second run is a verified cache hit with an identical sha256, and both are recorded.
- The timeline stays untracked.

## Result

Done. The timeline exists, validates, and reuses byte-identically. **Nothing below is a musical
finding**, and the wording is chosen so that none of it can be quoted as one.

### The artifact

`corpus/derived/sparse-funk-exposed-bass/timeline/song.timeline.json`, untracked, 4.8 MB.

```text
sha256:47e0178cc5b940c4545104c6c4eedb73b5f04d044f4e00b22dce23a583c977c4
cache key sha256:4808c534fb75376e0e2b2c49830721938c2189c19d1ecdb8133899b430849cd6
source_audio sha256:8ff73623...9aa628, 45.00 s, 48 kHz, stereo
stages: generate, separate, activity.measure, activity.interval, onset.spectral_flux
```

Second invocation: verified cache hit, same sha256. A `--force` recompile produced a file `cmp`
reports as byte-identical to the first. Appending one byte to the timeline produced a named miss and
a recompile back to the same hash; appending nine bytes to `vocals.wav` produced a refusal naming
both hashes and exit code 1; restoring it restored the hit.

### What came out, per model output

| output | samples | level min / median / max dBFS | intervals | covered | onsets | flux min / median / max |
| --- | --- | --- | --- | --- | --- | --- |
| `drums` | 1936 | -62.63 / -47.67 / -11.82 | 50 | 33.30 s, 74.0% | 153 | 29.5 / 548.7 / 1396.9 |
| `bass` | 1936 | -62.81 / -25.52 / -16.06 | 29 | 35.83 s, 79.6% | 95 | 32.9 / 107.6 / 326.0 |
| `other` | 1936 | -62.83 / -28.42 / -19.35 | 1 | 41.77 s, 92.8% | 97 | 26.4 / 135.7 / 222.5 |
| `vocals` | 1936 | -62.04 / -61.24 / -54.01 | 0 | 0.00 s, 0.0% | 0 | — |

`vocals`' row is the one to read carefully. Zero intervals and zero onsets means **this detector at
these thresholds claimed nothing about that model output**. It does not mean the output is empty, and
it emphatically does not mean nobody sang: `principle:1` and Henry's own gate 3 note both say so.

### Four mechanically interesting patterns, ungraded

**Everything stops around 40 seconds.** The last onset is at 39.97 s in `drums` and `bass` and
39.52 s in `other`, and `other`'s single interval ends at 41.77 s, in a file that runs 45.00 s. Five
seconds of the timeline carry no inference from any track. Whether that is a tail, a fade, or the
piece ending is a question for ears.

**The median inter-onset gap is 0.30-0.33 s on all three claimed tracks.** The specification
*requested* 96 BPM, at which an eighth note is 0.3125 s. That is a coincidence worth writing down and
nothing more: nothing in this pipeline has measured a tempo, the request is `requested` and stays
there, and a detector whose median gap resembles a subdivision is not evidence that the subdivision
exists. `principle:1` exists for exactly this sentence.

**The merge rule is doing real work on `drums`.** Fifty intervals, and sixty-two gaps closed to
produce them — more joins than intervals. The interval structure on that track is a property of the
100 ms merge rule at least as much as of the audio.

**Onset margins have a long floor.** The smallest margin over threshold is 4.77 on `drums`, 4.37 on
`bass` and 1.24 on `other`, against medians of 517, 68 and 72. Some hypotheses cleared the bar by a
hair. Those are the ones most worth clicking, and the Observatory carries the margin so they can be
found.

### What was not done

No verdict. Fifty intervals is fifty spans a threshold-with-memory produced; 153 onsets is 153
hypotheses one detector produced at one parameter set. Whether any of them corresponds to something
audible is gate 4, and gate 4 is answered by ears.
