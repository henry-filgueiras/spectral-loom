---
id: tsk_01M0GK89WR1EE5H17W3AJP7PFJ
sequence: 8
kind: task
status: pending
sprint: spr_01M0GK725M1JMHQH8PQVSMGS7Q
created: 2026-08-20
---

# Execute each pinned model once and record what backend it used

## Objective

Execute each pinned cabinet entry once on this machine, to establish the only claim a smoke can
support: this exact thing runs here, in this environment, on this backend.

A smoke is not an evidence gate. It does not say the separation is good or the notes are right;
gates 3 and 5 do that, with a human listening.

## Acceptance criteria

- Each of the three runs real inference once, on input small enough to be synthesized locally
  where that is sufficient to exercise the model.
- Recorded per model: the device actually selected, the package and runtime versions in play,
  success or failure, any warning that changes what the result means, and enough of the output's
  shape to show inference occurred rather than an object being constructed.
- Runtime output stays untracked unless something small and textual is deliberately promoted.
- Gate 1 either passes or has a precise recorded blocker. A blocker is not resolved by swapping
  a model without discussion.
