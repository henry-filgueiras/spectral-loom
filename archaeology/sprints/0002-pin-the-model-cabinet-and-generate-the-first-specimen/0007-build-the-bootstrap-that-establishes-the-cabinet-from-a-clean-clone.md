---
id: tsk_01M0GK89WMD1DQ4J6N41SWWZX8
sequence: 7
kind: task
status: pending
sprint: spr_01M0GK725M1JMHQH8PQVSMGS7Q
created: 2026-08-20
---

# Build the bootstrap that establishes the cabinet from a clean clone

## Objective

Write the first operational bootstrap under `scripts/`, to the contract `scripts/README.md`
already states, so that a clean clone can deliberately establish the local cabinet.

Its shape follows from the environment structure task:6 measures, not from a preference.

## Acceptance criteria

- Every requirement in `scripts/README.md`: exact immutable revisions, idempotent, verify before
  fetching, skip what already verifies, recover from a partial download, license and provenance
  recorded in tracked metadata, no arbitrary remote model code, writes only into ignored paths,
  human-invoked and never reached by a test or by CI.
- Idempotency demonstrated by measurement: run it, run it again, and prove from the second run
  that nothing was re-downloaded. Reading the code and concluding it skips is not evidence.
- The decisions the script makes — parsing the manifest, judging whether an asset verifies,
  computing paths — refactored into the package where that buys hermetic tests, and tested there.
- No test in the default suite touches the network or needs weights.
