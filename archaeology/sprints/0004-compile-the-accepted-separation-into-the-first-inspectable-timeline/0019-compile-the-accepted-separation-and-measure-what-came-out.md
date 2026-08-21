---
id: tsk_01M0GV2MEQ38AR91HZ6JR5H9T6
sequence: 19
kind: task
status: pending
sprint: spr_01M0GV19568TPVR34C47C2NPVD
created: 2026-08-20
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
