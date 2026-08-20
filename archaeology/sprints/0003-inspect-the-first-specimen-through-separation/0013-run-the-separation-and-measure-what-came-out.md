---
id: tsk_01M0GPWWCBJC3FXDA1EGYFXBWA
sequence: 13
kind: task
status: closed
sprint: spr_01M0GPVMBCYCX68KZF76QFQ5QS
created: 2026-08-20
closed: 2026-08-20
---

# Run the separation and measure what came out

## Objective

Run the stage once on the accepted 45-second specimen and record what actually happened, including
the diagnostics that a later gate would otherwise have to take on faith.

## Acceptance criteria

- Source hash verified against the receipt before inference.
- Exact command, backend, elapsed time, and every output path and hash recorded.
- Duration, sample rate and channel agreement checked across stems.
- A second identical invocation demonstrated to be a verified cache hit, with the timing that
  proves it.
- Cheap engineering diagnostics run and reported as diagnostics, not as musical judgements:
  readability, finiteness, unexpected all-zero stems, temporal offset, and the error between the
  stem sum and the source. No pass threshold is invented; the residual is measured and reported.
- No audio is committed.

## Result

Done. The pinned separator ran once on the accepted specimen, on MPS, and everything below is
measurement rather than opinion.

```
$ ./loom separate sparse-funk-exposed-bass

  source      corpus/generated/sparse-funk-exposed-bass/source.wav
  sha256      sha256:8ff73623a29d213b0732296c5dfbff1aa8908fc2a78647b14ed754209b9aa628
  accepted    sparse-funk-exposed-bass.8ff73623a29d.review.json
  separator   demucs.apply.apply_model
  revision    demucs==4.1.0 adefossez/HTDemucs@bf35a81b663819a8255c8fefee17f9d812b786b5
              htdemucs/955717e8
  device      mps
  cache key   sha256:504ed36f4e4107578d3af1ea954ce01e026780b6bee609fde9e16f7415af350e

  runtime     cpython3.11 darwin-arm64 mps
  load        0.128 s
  inference   2.345 s
  total       2.8 s
  warnings    none
```

### Outputs

All four at 44 100 Hz stereo, 1 984 500 frames = **45.000000 s exactly**, agreeing with each other
and with the source's 45.000000 s at 48 000 Hz. Every sample finite. No stem clipped on write and
none was clamped. Nothing is tracked.

```
htdemucs · drums   peak 0.90759  rms 0.071615  sha256:533be3f197852d7a4b546c66e383a6f743b84bdda1f72bb2c1822a39820f2b0f
htdemucs · bass    peak 0.51077  rms 0.059722  sha256:0b64d1ef4f3f5c439122ed8c210f76fac8be1c7f110e4046005b77096f0b8126
htdemucs · other   peak 0.41092  rms 0.060069  sha256:19de0df1ea4f8ef4edf17e75f7b6ee9ace908f0f496dc7bb5d663d4c127041c5
htdemucs · vocals  peak 0.00467  rms 0.000876  sha256:e4353ec05c8370ad0ed7ed44b3a8086214c492ed3ad2db2bd6c4aee6e2e4d082
diagnostics/reconstruction.wav   peak 0.90115  rms 0.113978
diagnostics/residual.wav         peak 0.05612  rms 0.003573
source (48 kHz, for reference)   peak 0.89127  rms 0.114063
```

### Diagnostics, uninterpreted

- **Temporal offset: 0 samples.** FFT cross-correlation of the channel mean of the source at the
  model's rate against the summed outputs peaks at lag 0. There is no unexplained offset.
- **Recombination residual: −30.11 dB** relative to the source, RMS 0.003562, peak 0.056.
- **No stem is all zeros.** The lowest, `vocals`, is RMS 0.000876 and 0.47 % of full scale — very
  quiet, not silent, and *not* evidence that the source contains no voice. It is what HTDemucs
  assigned to that output and nothing more.
- **Zero-sample fraction** per stem: drums 0.3 %, bass 0.1 %, other 0.0 %, vocals 0.0 %.

**No pass threshold was invented and none is asserted.** Demucs is not trained to reconstruct
additively and the outputs were written as 16-bit PCM, so a nonzero residual is expected; −30.11 dB
is a number to compare the *next* run against, not a grade.

### The residual was corroborated by a different code path

The stage computes its residual through `demucs.audio.convert_audio` (julius). An independent check
using `scipy.signal.resample_poly(441/480)` and NumPy — a completely separate resampler and a
separate summation — produced RMS 0.003563 and **−30.11 dB**. Agreement to four decimal places
means the number is a property of the separation rather than of this project's arithmetic.

### Cache hit, demonstrated three ways

```
first run            3.32 s wall,  2.345 s inference
second run           0.11 s wall,  "cache hit: reused a previous separation,
                                    after re-hashing every file it declares"
```

A ~30× difference, and the second run re-read and re-hashed 47 MB to get it. It is a verified hit,
not an assumed one, and the two negative controls prove the verification does something:

- **appending nine bytes to `vocals.wav`** → refused, naming the file: *"no longer hashes to what
  the manifest recorded; a manifest describing a file that has since changed is not a cache entry"*.
  Restoring the file restored the hit.
- **`--device cpu`** → refused, printing both cache keys, because a different backend is a different
  result and the existing directory is not one for that request. Not overwritten.

### One mechanical observation, offered as a question rather than a finding

Pairwise correlation of stem amplitude envelopes: `bass × other` **+0.165**, everything else within
±0.05 of zero. That is consistent with two parts that play at the same times and consistent with
leakage between them, and this round cannot tell the difference. It is a reason to listen to `bass`
and `other` against each other, not a conclusion about either.

### Not done, on purpose

No timeline, no activity detection, no onsets, no Basic Pitch, no projection, no second specimen.
**Nobody has heard the stems.** Everything above is engineering measurement, and none of it is
entitled to an opinion about whether the bass is actually isolated.
