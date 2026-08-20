---
id: tsk_01M0GK8VWDZ5SYGXA2Y961FCKA
sequence: 10
kind: task
status: pending
sprint: spr_01M0GK725M1JMHQH8PQVSMGS7Q
created: 2026-08-20
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
