---
id: tsk_01M0GPWWCBJC3FXDA1EGYFXBWA
sequence: 13
kind: task
status: pending
sprint: spr_01M0GPVMBCYCX68KZF76QFQ5QS
created: 2026-08-20
---

# Run the separation and measure what came out

## Objective

Run the stage once on the accepted 45-second specimen and record what actually happened, including
the diagnostics that a later gate would otherwise have to take on faith.

## Acceptance criteria

- Source hash verified against the receipt before inference.
- Exact command, backend, elapsed time, and every output path and hash recorded.
- Duration, sample rate and channel agreement checked across stems.
- A second identical invocation demonstrated to be a verified cache hit, with the timing that
  proves it.
- Cheap engineering diagnostics run and reported as diagnostics, not as musical judgements:
  readability, finiteness, unexpected all-zero stems, temporal offset, and the error between the
  stem sum and the source. No pass threshold is invented; the residual is measured and reported.
- No audio is committed.
