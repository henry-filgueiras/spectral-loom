---
id: drg_01M0GH6ETFHGC354FJPB7ENSP1
sequence: 2
kind: dragon
status: closed
created: 2026-08-20
---

# The model cabinet may not resolve into a single Python environment

## Context

decision:5 asserts that ACE-Step, Demucs, and Basic Pitch will not resolve into one Python
environment. That assertion is currently unmeasured: no resolver has been run, no wheel has been
downloaded, and the belief comes from reading published constraints rather than from an attempt.

The architecture already hedges against it — stages communicate through files, not imports — but
the hedge has a cost that is only worth paying if the risk is real.

## Question

Do the three models co-exist in one Python 3.11 environment on Apple silicon, and if not, which
pairs do?

## Constraints

- The host is macOS on Apple silicon; CUDA-only paths are not available and MPS support differs
  per model.
- The default environment must stay light regardless of the answer, so this is a question about
  the *optional* groups, not about the base install.
- Nothing may be pinned to a moving branch, so the answer must be recorded as exact revisions.

## Candidate direction

Attempt resolution in the model-bootstrap round, one model at a time, recording the exact
resolved sets. Prefer optional dependency groups where a pair resolves. Fall back to separately
managed pinned environments invoked as subprocesses across the timeline file boundary only where
resolution genuinely fails.

## Resolution criteria

Closed when each of the three models has a pinned, reproducible environment recipe that has
actually been installed and run once, and the record states which of them share an environment
and which do not.

## Resolution (2026-08-20)

**They co-exist. All three, in one Python 3.11 environment, on Apple silicon.** The expectation in
decision:5 was wrong, and it was wrong in the way unmeasured expectations usually are: it was
derived from published constraints that no longer describe these packages.

### What was measured

The optimistic attempt first, as the dragon asked. `uv pip compile` over `diffusers==0.40.0`,
`transformers==5.15.1`, `torch==2.13.0`, `accelerate`, `soundfile`, `demucs==4.1.0`, and
`basic-pitch==0.4.0` resolved on the first try into 78 packages, with numpy 2.4.6, torch 2.13.0,
and coremltools 9.0. Installation took 17 seconds. Every one of `torch`, `diffusers`,
`transformers`, `demucs`, `basic_pitch`, `coremltools`, `soundfile`, and `sphn` imported, and
`diffusers.AceStepPipeline` resolved to a real class.

The specific prediction decision:5 made — "one of them wants TensorFlow-family runtime while
another wants Torch" — does not hold on this platform. basic-pitch 0.4.0's own environment markers
install TensorFlow only on non-Darwin, and `tensorflow-macos` only above Python 3.11. On macOS at
3.11 they install **coremltools and nothing else**, so there is no TensorFlow in the environment
at all and nothing for Torch to disagree with. The conflict that was feared is an artifact of a
different platform.

### Installation is not execution, and keeping them apart caught a real failure

The dragon asked for them to be kept apart, and keeping them apart is what caught the failure that
resolution could not see. The environment resolved, installed, and imported `basic_pitch`
successfully — and then `import basic_pitch.inference` raised `ModuleNotFoundError: No module named
'pkg_resources'`, three levels down: basic-pitch caps resampy below 0.4.3, resampy 0.4.2 imports
`pkg_resources` at module scope, and setuptools removed `pkg_resources` in version 81. Pinning
`setuptools==80.9.0` fixes it. See [[drg_01M0J0K6BJ5G4G3EVXDG8SR1MJ]] for what that pin costs
later.

Nothing analogous happened to Demucs or ACE-Step: for those two, resolution predicted runtime
exactly.

### Backends actually selected, on Apple M5 Pro / 24 GiB / macOS 26.4.1 / torch 2.13.0

| entry | backend | evidence |
| --- | --- | --- |
| ACE-Step | **MPS** | `pipeline.transformer.device` reported `mps:0`, dtype `torch.bfloat16`; 10 s of 48 kHz stereo in 8.9 s after a 7.3 s load |
| Demucs | **MPS** | `apply_model(..., device="mps")` returned `[1, 4, 2, 88200]`, all finite |
| Basic Pitch | **CoreML** | loaded `nmp.mlpackage`; TF, ONNX, and TFLite all absent |

Nothing fell back to CPU silently. No package claimed acceleration it did not deliver.

Basic Pitch is the one whose backend is worth restating: it is not on MPS and never will be,
because it is not a Torch model here. Which of its four bundled serializations executes is decided
at import time by whichever runtime is importable, which makes the selected serialization a
property of the resolved environment rather than a choice — and part of what produced any note.

### What this changes

The cabinet is **one optional dependency group**, `[project.optional-dependencies].cabinet`,
materialized by `scripts/bootstrap_cabinet.py env` into `.venv-cabinet/` from the same committed
lockfile. Not `.venv`: syncing torch into the environment that runs ruff and pytest means the next
plain `uv sync` tears it out again. Two environments, one resolution.

No subprocess boundary is needed for the generation stage, so none was built. The architectural
hedge stays — stages still talk through hashed files and a stage may still run somewhere else —
because it is free, and because the next model added to the cabinet is the one that may cost it.

The base environment is unchanged in weight: `uv sync` installs eighteen packages and no model.

### What this cost

One platform. The cabinet cannot be locked for Intel macOS at all, because demucs 4.1.0 caps torch
below 2.3 there and diffusers needs 2.6+. `tool.uv.environments` now excludes it, which is a
narrowing of support recorded as [[dec_01M0HZTHF08Y3QRJEA7SPS7SFY]] rather than left as a resolver
accident.

### Left unmeasured

The Linux half of the lockfile resolves — TensorFlow 2.15, numpy 1.26 — and **has never been
installed or run by anyone in this project.** Everything above is a measurement about one Apple
silicon host. A second host is a second measurement, not a reasonable inference from this one.
