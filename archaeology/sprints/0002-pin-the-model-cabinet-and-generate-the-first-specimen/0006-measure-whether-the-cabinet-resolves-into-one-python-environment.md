---
id: tsk_01M0GK89WG8Z8NXNAZZC06EFB5
sequence: 6
kind: task
status: closed
sprint: spr_01M0GK725M1JMHQH8PQVSMGS7Q
created: 2026-08-20
closed: 2026-08-20
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

## Result

Done, and the dragon is closed. The full measurement is in
[[drg_01M0GH6ETFHGC354FJPB7ENSP1]]; the short version is that **all three co-exist in one Python
3.11 environment on Apple silicon**, on the first resolver attempt, and decision:5's expectation
that they would not was wrong.

Two things this task produced that the dragon's closure does not repeat.

**The optimistic attempt was the right order, and it saved building three environments nobody
needed.** Had this round started by isolating them "because trouble was predicted", the prediction
would have been confirmed by construction and the dragon would have closed on an assumption.

**Separating "resolution succeeded" from "the model executed once" earned its keep exactly once,
and that once was enough to justify the discipline.** Basic Pitch resolved, installed, and
imported — and then `import basic_pitch.inference` died on `pkg_resources`, removed from setuptools
81, reached for by resampy 0.4.2, which basic-pitch pins below the release that fixed it. A
resolver cannot see a module-scope import of an undeclared dependency. Only running it can.
`setuptools==80.9.0` is now in the cabinet extra for that reason and no other, and
[[drg_01M0J0K6BJ5G4G3EVXDG8SR1MJ]] is open about what that pin costs later.

The cost of coexistence was one platform: Intel macOS cannot be locked at all, because demucs 4.1.0
caps torch below 2.3 there while diffusers needs 2.6+. Recorded as
[[dec_01M0HZTHF08Y3QRJEA7SPS7SFY]] rather than left as a resolver accident.

The base environment is unchanged: `uv sync` still installs eighteen packages and no model. The
cabinet is an optional extra materialized into `.venv-cabinet/` from the same lockfile, so
stocking it does not destroy the environment that runs ruff and pytest, and a `uv sync` afterwards
does not tear it out.
