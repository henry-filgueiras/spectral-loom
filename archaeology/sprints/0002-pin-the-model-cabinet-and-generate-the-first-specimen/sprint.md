---
id: spr_01M0GK725M1JMHQH8PQVSMGS7Q
sequence: 2
kind: sprint
status: active
created: 2026-08-20
---

# Pin the model cabinet and generate the first specimen

## Goal

Turn the model cabinet from three names into three pinned, installed, executed identities, and
then use it exactly once: generate a single candidate WAV for `sparse-funk-exposed-bass` and stop
so Henry can listen to it.

This is gate 1 of `docs/roadmap.md` in full, plus the narrowest possible slice of gate 2 — the
generation, not the acceptance. Acceptance is Henry's, and it is not this sprint's to claim.

## Rationale

Everything downstream of here is expensive and slow to judge. Separation, timeline inference,
and projections all read artifacts produced by models nobody in this repository has run, at
revisions nobody has resolved, in an environment nobody has attempted to build. Building any of
that on top of an unpinned cabinet would produce results that cannot be attributed to an input,
which is the failure the whole evidence-gate ladder exists to prevent.

There is also a specific unmeasured belief to settle. [[drg_01M0GH6ETFHGC354FJPB7ENSP1]] says the
three models may not co-exist in one Python environment and is open precisely because the belief
came from reading published constraints rather than from running a resolver. A sprint that pins
the cabinet without attempting the install would leave that dragon exactly as open as it started.

And one WAV is the smallest object that can fail informatively. A corpus of a thousand generated
songs nobody has heard is a thousand unusable songs; one specimen, listened to, either survives
human ears or produces a recorded reason it did not.

## Success criteria

- Every cabinet entry has an exact, immutable identity for **each** thing that has one: the
  implementation that executes, the model assets that are loaded, and the runtime whose behaviour
  materially affects inference. Where upstream gives code and weights separate identities, both
  are recorded rather than flattened into one fictional revision.
- A tracked cabinet manifest answers "what did this project mean by ACE-Step, Demucs, and Basic
  Pitch at this point in history" from a clean clone, with licenses and upstream-published hashes,
  without consulting a moving branch.
- `trust_remote_code` and its equivalents stay off. A model that genuinely requires arbitrary
  remote code is a recorded finding, not a quietly weakened rule.
- The coexistence question in [[drg_01M0GH6ETFHGC354FJPB7ENSP1]] is answered by measurement:
  which of the three share an environment, which do not, and what actually prevented it.
  "Resolution succeeded" and "the model executed once" are recorded as separate facts.
- A bootstrap under `scripts/` satisfies the contract in `scripts/README.md`, and its idempotency
  is demonstrated by running it twice and measuring the second run, not by reading the code.
- Each of the three has executed once on this machine, with the device it actually selected
  recorded — including any silent fall back to CPU.
- `spectral-loom doctor` reports cabinet state without mutating anything and without downloading
  anything, keeping bootstrap health separate from inference readiness.
- One 30-60 second candidate exists for `sparse-funk-exposed-bass`, generated from the tracked
  specification at a pinned revision, with a manifest that records only what was observed about
  the file and never restates the prompt as fact.
- The default environment stays light, the hermetic suite stays hermetic, and nothing heavyweight
  is tracked.

## Non-goals

- Deciding whether the candidate is any good. Henry is the gate 2 oracle.
- Meaningful Demucs separation of the specimen. The Demucs smoke exists to prove the pinned thing
  runs, and a smoke is not an evidence gate.
- Any `song.timeline.json` inferred from real audio.
- Basic Pitch anywhere in the compiler beyond its smoke.
- Any projection, renderer, or shader.
- Corpus generation of any size above one.
- A generalized model-plugin architecture, a job scheduler, or a cache framework. Three models is
  not enough cases to generalize from.
- Pushing commits.
