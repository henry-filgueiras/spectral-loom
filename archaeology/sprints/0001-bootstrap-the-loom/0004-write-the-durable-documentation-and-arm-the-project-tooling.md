---
id: tsk_01M0GH7R5NY2B61F37X7Z4JW2B
sequence: 4
kind: task
status: closed
sprint: spr_01M0GH70AX635WAS8M3SQQRV9W
created: 2026-08-20
closed: 2026-08-20
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

## Result

Done. Documentation, the example specification, CI, and WitnessGlass arming.

**Documentation.** `docs/architecture.md` states the four layers and the invariants — including
that a negative inference proves nothing and that a projection may never write to the timeline it
read. `docs/provenance.md` defines the envelope by the seven questions it must answer and states
that the provenance record and the cache key are the same information. `docs/roadmap.md` is nine
evidence gates with an explicit deferral list. `CLAUDE.md` carries the durable working rules.
`scripts/README.md` defines a boundary with no scripts behind it: the model-bootstrap contract,
written before the first script exists.

**Example specification.** `corpus/specs/example.yaml` requests a 45-second sparse funk
instrumental with exposed bass, drums, and clean guitar at a requested 96 BPM in a requested D
minor, seed 20260820, with `generator.revision: null` — deliberately unresolved, with the null
documented as something that must *block* generation rather than resolve to whatever `main` is
that day. It validates, and a CLI test asserts the word UNPINNED appears in its output.

**CI.** Format, lint, strict types, schema drift, tests, the example specification, and `doctor`,
on Python 3.11, installed with `uv sync --locked`. Read-only permissions, no publish step. All of
it was run locally first and passes; the workflow itself has not run on GitHub, because nothing
has been pushed.

**WitnessGlass.** Armed by the mechanism its own `logs/0001` documents for external projects,
which is not `scripts/arm.sh` — that script is bound to the WitnessGlass checkout. Recorded as
[[dec_01M0GHZ70T3P07ZAMNCENVZQ9H|Be observed by WitnessGlass without vendoring it]]; the arming procedure and its verification are in [[log_01M0GJ17Y731YQVJPA497NPGTB|Bootstrapping Spectral Loom: what the host lacked and how the recorder was armed]].
