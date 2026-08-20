---
id: tsk_01M0GPWWCJ72WZPT95M103773B
sequence: 15
kind: task
status: pending
sprint: spr_01M0GPVMBCYCX68KZF76QFQ5QS
created: 2026-08-20
---

# Watch the pinned cabinet stay remotely resolvable

## Objective

A pin establishes identity, not availability. Notice, on a schedule, when a pinned cabinet artifact
stops being resolvable — before a clean clone discovers it during a bootstrap.

## Acceptance criteria

- An explicitly networked script checks metadata only and downloads no weights.
- Per asset it distinguishes, as far as the provider actually establishes: repository reachable,
  pinned revision reachable, expected paths present, declared size and identity metadata still
  compatible, gated or authentication-required, transient provider failure, and unavailable for
  an unknown reason. An artifact is not called deleted unless the provider says so.
- Human-readable and `--json` output.
- A scheduled workflow, separate from hermetic PR CI, runs it roughly weekly with network
  explicitly permitted, downloads nothing, infers nothing, mutates nothing, and fails with a
  useful summary.
- No automatic cabinet update and no recovery mechanism. Choosing a replacement is a later,
  explicit experiment.
- Classification logic is tested hermetically against recorded provider responses.
