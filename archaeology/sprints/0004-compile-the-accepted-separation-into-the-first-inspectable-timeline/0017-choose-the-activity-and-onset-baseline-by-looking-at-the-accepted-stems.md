---
id: tsk_01M0GV2ME46CYT9G8E1B8J9GTX
sequence: 17
kind: task
status: pending
sprint: spr_01M0GV19568TPVR34C47C2NPVD
created: 2026-08-20
---

# Choose the activity and onset baseline by looking at the accepted stems

## Objective

Decide what `activity.sample`, `activity.interval` and `onset` are going to *mean* by looking at
the accepted stems, before any of it is implemented — and record which parameters were chosen from
evidence and which are arbitrary baselines.

## Acceptance criteria

- The distributions that matter are measured on the accepted stems rather than assumed: per-frame
  level for every model output, and the novelty statistic the onset detector will use.
- The chosen thresholds are shown to sit in a region where the answer barely moves, so they are a
  plateau rather than a fit to one specimen.
- Absolute level stays visible in the rule. No per-stem normalization that would let the loudest
  noise in a near-silent output become "active".
- Every parameter that can change an event is enumerated, with a reason, and marked as evidence-led
  or arbitrary.
- What would justify changing each one later is written down.
- A dragon is opened if touching the data made "activity" less obvious than the roadmap assumes.
