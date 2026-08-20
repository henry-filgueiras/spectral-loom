---
id: tsk_01M0GK8VWDZ5SYGXA2Y961FCKA
sequence: 10
kind: task
status: closed
sprint: spr_01M0GK725M1JMHQH8PQVSMGS7Q
created: 2026-08-20
closed: 2026-08-20
---

# Generate one candidate specimen and stop for human ears

## Objective

Implement the smallest generation stage that turns the tracked `SongSpec` into one candidate WAV
with an auditable manifest, and use it exactly once. Then stop, because the next thing that
happens is a human listening.

The stage belongs in the package, not in `scripts/`; `scripts/` is machine setup.

## Acceptance criteria

- Reads the existing `SongSpec` and refuses to run when the generator identity is not pinned.
- `corpus/specs/example.yaml` updated to the resolved identity, including any correction to the
  placeholder `generator_params` that the real pinned interface shows to be wrong — smallest
  evidence-backed change, with the reason recorded.
- Output lands in an ignored specimen-specific location alongside a manifest that records which
  specification produced it, the hash of that specification, the exact implementation and asset
  identities, the seed, the parameters that mattered, the runtime and backend, and the observed
  hash, duration, sample rate, and channel count of the file.
- The manifest states only what was observed about the artifact. Requested values appear labelled
  as requests or not at all. No BPM, key, or instrument is reported as a fact about the audio
  because it appeared in the prompt.
- Unchanged inputs at an unchanged revision with unchanged material parameters do not burn another
  inference run, and the reuse rule is explicit rather than emergent. No general cache framework.
- Exactly one candidate generated, 30-60 seconds, from the tracked specification's seed unless the
  real interface forces a justified change. Its path, hash, and duration reported prominently, with
  a convenient way for Henry to listen — and nothing downstream of it attempted.

## Result

Done, and **stopped**. One candidate exists. Nobody has heard it.

```
corpus/generated/sparse-funk-exposed-bass/source.wav
  sha256      8ff73623a29d213b0732296c5dfbff1aa8908fc2a78647b14ed754209b9aa628
  duration    45.000000 s     (ffprobe, independent of this project's own reader)
  format      pcm_s16le, 48000 Hz, 2 channels, 8,640,044 bytes
  level       RMS -18.85 dBFS — audio, not silence, not clipped
  runtime     cpython3.11 darwin-arm64 mps
  inference   15.7 s
```

`afplay corpus/generated/sparse-funk-exposed-bass/source.wav`

### The specification's placeholders were all three wrong

`guidance_scale: 7.5` — the turbo checkpoint is guidance-distilled and the pipeline logs "Guidance
scale 7.0 is ignored for turbo (guidance-distilled) checkpoints". Keeping it would have put a value
in the cache key that changes nothing about the result: an invalidation that invalidates nothing.
`scheduler: euler` — not a call parameter; it is a pipeline component loaded from the checkpoint.
`audio_format: wav` — not the generator's business; the pipeline returns tensors and this project
chooses to write WAV.

Replaced with `num_inference_steps: 8`, `shift: 3.0`, `dtype: bfloat16` — the turbo defaults,
restated rather than inherited, so that an upstream default change becomes a diff instead of a
silent re-render. The specification is also now pinned to
`ACE-Step/acestep-v15-xl-turbo-diffusers@200ba991ae448051e14b0183157e35c2d27c9fb0`, and its
`model_id` corrected: it named `ACE-Step/ACE-Step-v1.5`, which is not a repository that exists.

### The truth-layer rule, made structural rather than remembered

`GenerationManifest` is a third contract with its own schema. Observations of the file —
hash, duration, sample rate, channels — live in `source_audio`. The prompt, the seed, and the
requested tempo live in a provenance stage whose `truth_layer` is `requested`, under keys named
`requested_bpm`, `requested_keyscale`, `requested_timesignature`. They are in the key because the
pinned interface really does take them as conditioning, and they really do change the output. They
are still requests: `requested_bpm: 96` says the model was told 96 and says nothing about what came
back.

A test serializes the manifest with the requested stage removed and asserts that `"96"`,
`"D minor"`, and `"electric bass"` appear nowhere in what remains.

### Reproducibility, measured

The same specification, seed, parameters, and revision produced a **byte-identical** file across
two further `--force` runs in a separate process against a separate output root:
`8ff73623…9aa628` all three times. MPS is deterministic here for this pipeline, which is what the
project's cache invariant needs and had not been checked.

Reuse works from the provenance record rather than from a cache framework: spec hash, tool, tool
revision, parameters, plus re-hashing the audio against what the manifest recorded. A second
`generate` on unchanged inputs took 0.1 s against 18.8 s and did not import torch. A manifest
describing a file that has since changed is not a cache hit — it is a document making a false
claim — and that is a test.

### Refusals

Generation refuses a null revision, a revision that disagrees with the cabinet, a `model_id` that
disagrees with the cabinet, a `generator_params` key the pinned interface does not take, and a
`generator_params` key the adapter owns. All before a weight is loaded, because a mismatch found
after an eleven-gigabyte load is the same mismatch found for the price of reading two files. There
is no override flag.

### What was deliberately not done

Demucs has not touched this file. No timeline exists. Nothing has been rendered. **No judgement has
been made about whether the music is any good** — that is Henry's, and gate 2 is not passed by
producing a file. The questions are the ones the specification's own notes ask: is the bass audible
and exposed, is there useful silence between phrases, are the parts separable by ear, is there
vocal bleed or another generator failure. A rejection gets recorded, with what was wrong, before
anything is changed and another candidate is made.
