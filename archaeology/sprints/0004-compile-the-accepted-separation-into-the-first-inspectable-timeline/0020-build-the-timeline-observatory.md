---
id: tsk_01M0GV2MF10J4KTCFQZP0CXG3V
sequence: 20
kind: task
status: pending
sprint: spr_01M0GV19568TPVR34C47C2NPVD
created: 2026-08-20
---

# Build the Timeline Observatory

## Objective

Build the smallest local surface that lets Henry falsify a timeline claim with his ears: click an
onset, hear the moment, and A/B the stem against the source mix.

## Acceptance criteria

- Loopback only, no external script, stylesheet, font or service, one shared Web Audio clock, audio
  served from the artifacts that already exist, generated assets ignored.
- Aligned lanes for the source, the selected stem, the activity measurement, the inferred intervals,
  and the onset hypotheses.
- The activity lane makes the rule visible: the measured curve, the enter and exit thresholds, and
  the intervals the rule produced.
- Clicking an onset seeks to it, loops a short window around it, and lets the stem and the source
  mix be swapped with one key.
- Clicking an interval loops it with a small context margin; an activity sample reveals its measured
  value and the thresholds it was compared against.
- Selecting an event shows its exact semantic record — type, times, confidence only where one truly
  exists, raw score, evidence artifact and hash, producing stage, and the parameters relevant to
  that claim — without requiring anyone to read JSON.
- Absence renders as absence of inference: zero intervals is reported as zero inferred under a
  stated rule.
- Any exploratory overlay is labelled hypothetical and cannot write to the timeline, its cache, or
  its review state.
- The same short region can be looped while switching among source and every model output, with the
  timeline claims staying aligned.
- The command is reachable through `./loom`.
