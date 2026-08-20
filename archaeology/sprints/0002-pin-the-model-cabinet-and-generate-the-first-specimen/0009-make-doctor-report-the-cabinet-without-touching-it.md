---
id: tsk_01M0GK8VW9S47B4AJ2SYRT9FDV
sequence: 9
kind: task
status: pending
sprint: spr_01M0GK725M1JMHQH8PQVSMGS7Q
created: 2026-08-20
---

# Make doctor report the cabinet without touching it

## Objective

Teach `spectral-loom doctor` to report the cabinet now that the cabinet has a real pinned identity
and a real installation layout, while keeping it what it already is: an observer that changes
nothing.

## Acceptance criteria

- Distinguishes states that are genuinely different: an entry known and pinned in the manifest, a
  runtime environment present or missing, assets present or missing, assets verified or merely
  present, and backend availability where that is cheap to know.
- Never downloads, never writes, never imports a model to find out. A `doctor` that has to load
  eleven gigabytes to answer a question is not a doctor.
- Bootstrap health and inference readiness stay separate, as the CLI's exit codes already intend:
  an unstocked cabinet is information and exits zero.
- `--json` stays useful to a machine.
- Covered by hermetic tests that construct cabinet states on disk rather than requiring one.
