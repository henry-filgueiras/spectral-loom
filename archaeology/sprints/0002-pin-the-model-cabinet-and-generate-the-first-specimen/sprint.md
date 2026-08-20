---
id: spr_01M0GK725M1JMHQH8PQVSMGS7Q
sequence: 2
kind: sprint
status: closed
created: 2026-08-20
closed: 2026-08-20
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

## Retrospective (2026-08-20)

Every success criterion met. Six tasks closed, two decisions, one dragon closed against
measurement, one dragon opened. **Gate 1 passes. Gate 2 has a candidate and no verdict.**

### What the round changed about what this project believed

**decision:5 was wrong about the thing it was least sure of, and dragon:2 existed because it knew
that.** All three models resolve into one Python 3.11 environment on Apple silicon, on the first
resolver attempt, in seventeen seconds. The specific prediction — TensorFlow-family against Torch —
does not hold here: basic-pitch's own markers install TensorFlow only off Darwin, so on macOS at
3.11 there is no TensorFlow in the environment for Torch to disagree with. The architecture's
subprocess hedge was not needed and was not built.

**"A model revision" is not a unit of pinning.** ACE-Step and Demucs each have two independent
identities — the released implementation and the weights repository — and Basic Pitch has one,
because it ships its weights inside its wheel. A manifest that offered one revision per model would
have named things that do not exist. This is the round's most portable finding.

**The `trust_remote_code` rule was load-bearing on contact.** Every ACE-Step 1.5 checkpoint in
transformers layout is `custom_code`. The rule cost this project the smaller checkpoint and bought
it a path where no `.py` is ever fetched from a model host.

**Resolution and execution are genuinely different facts, and the discipline paid for itself
once.** Basic Pitch resolved, installed, imported — then died three levels down on a module-scope
`import pkg_resources` that setuptools removed in 81 and that resampy still reaches for because
basic-pitch caps it below the fix. No resolver can see that. Only running it can.

**Generation is byte-reproducible on MPS.** Same specification, seed, parameters, and revision
produced an identical sha256 across three runs in separate processes against separate output roots.
The project's cache invariant assumed something like this and had never checked.

### What exists that did not

`model-cabinet.toml`, and `spectral_loom.cabinet` to read it — stdlib-only, so `doctor` can report
a cabinet from an environment containing none of it. `scripts/bootstrap_cabinet.py` and
`scripts/smoke_cabinet.py`, the first two scripts in a directory that until now held only a
contract. A `GenerationManifest` contract and its schema. A `generate` command. A `doctor` that
distinguishes pinned from installed from present from verified. 118 hermetic tests, up from 87.

11.2 GB of weights on this machine, none of it tracked. One 45-second WAV, untracked.

### Two habits worth keeping

**The negative control.** Run 2 of the bootstrap succeeded with every outbound socket raising, which
proves nothing on its own — a guard that never fires is indistinguishable from a guard that does not
work. Pointing the same guard at an empty cabinet and watching it raise
`NetworkAccessError: outbound connection attempted to ('huggingface.co', 443)` is what turned
"nothing was downloaded" into evidence.

**Refusing to overwrite bytes that do not match.** The bootstrap stops rather than re-fetching over
a mismatched file. Wrong bytes are evidence about something, and this project does not get to
destroy them to make a run succeed.

### What is unmeasured, stated so a later round does not mistake it for settled

- **The music.** Nobody has heard the candidate. `sha256:8ff73623…9aa628` is a fact; whether the
  bass is exposed is not, and this round is explicitly not entitled to an opinion.
- **The Linux half of the lockfile** resolves — TensorFlow 2.15, numpy 1.26 — and has never been
  installed or run by anyone. Everything measured here is about one Apple silicon host.
- **CI has still never run.** Nothing has been pushed. The workflow now has to survive a lockfile
  carrying a TensorFlow resolution, which it has never been asked to do.
- **Demucs and Basic Pitch have executed only against sine waves.** They run. Whether they are any
  good on real audio is gates 3 and 5.
- **[[drg_01M0J0K6BJ5G4G3EVXDG8SR1MJ]]** is the honest statement about the Basic Pitch entry: it
  works today because of a pin on the last setuptools that carries a module upstream has removed.

### Next

Henry listens. `afplay corpus/generated/sparse-funk-exposed-bass/source.wav`. A rejection is
recorded — including what was wrong with it — before the prompt changes and another candidate is
made. An acceptance opens gate 3, where Demucs finally meets something that is not a sine wave and
the stems get heard.
