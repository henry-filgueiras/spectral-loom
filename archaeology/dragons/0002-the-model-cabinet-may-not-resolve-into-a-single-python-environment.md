---
id: drg_01M0GH6ETFHGC354FJPB7ENSP1
sequence: 2
kind: dragon
status: open
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
