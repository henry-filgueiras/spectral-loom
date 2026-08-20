---
id: tsk_01M0GH7R5NY2B61F37X7Z4JW2B
sequence: 4
kind: task
status: pending
sprint: spr_01M0GH70AX635WAS8M3SQQRV9W
created: 2026-08-20
---

# Write the durable documentation and arm the project tooling

## Objective

Write the durable documentation — README, architecture, provenance, roadmap — plus `CLAUDE.md`,
the example corpus specification, the scripts contract, and the CI workflow. Arm the repository
for WitnessGlass using the mechanism its own archaeology documents for external projects.

## Acceptance criteria

- Architecture states the four layers and the invariants, including that a negative inference is
  not proof of absence and that projections cannot mutate observations.
- Provenance defines an envelope that answers input, model and revision, parameters, runtime,
  duration, emitted hashes, and truth layer.
- Roadmap is a ladder of evidence gates with explicit deferrals, including no Spotify or
  streaming-service capture.
- One example specification exists for a future instrumental specimen, unexecuted, with a fixed
  seed and an unresolved-but-pinned-by-contract generator revision, and it validates.
- CI runs lint, format check, mypy, pytest, and the schema drift check on Python 3.11 from the
  committed lockfile.
- WitnessGlass is armed without vendoring, copying, or submoduling it, without modifying
  `~/witnessglass`, and without committing recordings.
