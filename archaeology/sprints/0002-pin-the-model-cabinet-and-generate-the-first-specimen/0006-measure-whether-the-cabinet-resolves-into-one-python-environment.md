---
id: tsk_01M0GK89WG8Z8NXNAZZC06EFB5
sequence: 6
kind: task
status: pending
sprint: spr_01M0GK725M1JMHQH8PQVSMGS7Q
created: 2026-08-20
---

# Measure whether the cabinet resolves into one Python environment

## Objective

Answer the question [[drg_01M0GH6ETFHGC354FJPB7ENSP1]] asks, by running a resolver rather than by
predicting one: do ACE-Step, Demucs, and Basic Pitch co-exist in one Python 3.11 environment on
Apple silicon, and if not, which pairs do and what actually stops the rest?

Start from the optimistic attempt. Building three isolated environments because trouble was
predicted would leave the dragon exactly as unmeasured as it is now.

## Acceptance criteria

- Recorded evidence for: all three together, and each failing subset down to whatever does
  resolve, naming the conflicting requirement rather than summarizing it.
- "Dependency resolution succeeded" and "the model executed once" recorded as separate facts,
  because a resolver's success says nothing about whether an import works.
- The backend each model actually selects on this host, measured — including anything that claims
  acceleration and silently runs on CPU.
- The base `spectral-loom` environment unchanged in weight regardless of the outcome.
- Whatever isolation the evidence justifies, and nothing more: optional dependency groups if they
  resolve, separate pinned environments across the file boundary only where they genuinely do not.
- [[drg_01M0GH6ETFHGC354FJPB7ENSP1]] closed or updated against its own resolution criteria.
