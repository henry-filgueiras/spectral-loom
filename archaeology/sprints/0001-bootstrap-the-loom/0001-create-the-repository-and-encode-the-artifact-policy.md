---
id: tsk_01M0GH7R4PJW1Y5X8D8SQ92JCV
sequence: 1
kind: task
status: closed
sprint: spr_01M0GH70AX635WAS8M3SQQRV9W
created: 2026-08-20
closed: 2026-08-20
---

# Create the repository and encode the artifact policy

## Objective

Create the repository, its public GitHub remote, the Python 3.11 / uv project skeleton with a
committed lockfile, and encode the artifact policy in `.gitignore` so that no untrackable class
of artifact can be staged by accident.

## Acceptance criteria

- `git init -b main`, `origin` pointing at a public `henry-filgueiras/spectral-loom`, no push.
- `pyproject.toml` with a `src/` layout, `requires-python == 3.11.*`, and a committed `uv.lock`.
- Ruff, mypy, and pytest configured and runnable.
- `.gitignore` covers weights, caches, virtualenvs, generated audio, derived stems, experimental
  timelines, rendered video, WitnessGlass recordings, and benchmark output, while leaving
  `corpus/specs/` and `archaeology/` tracked.

## Result

Done, with two prerequisites that had to be created rather than found.

**Neither `uv` nor Python 3.11 was present on the host.** `git` 2.53.0, `gh` 2.96.0, and `ffmpeg`
8.1 were. `uv` was installed from Homebrew (0.12.5) and CPython 3.11.16 by `uv python install
3.11`. This is worth recording because [[dec_01M0GH3HAHBCYE2HE8MGDEKWS0|Build on Python 3.11 with uv as the environment authority]] reads as though it merely ratified the
local environment, and it did not: the environment was built to match the decision.

**The remote.** `gh auth status` names `henry-filgueiras`; `henry-filgueiras/spectral-loom` did
not exist, so no collision. Created public with `gh repo create --source=. --remote=origin` and
deliberately without `--push`. The remote is empty and stays empty until Henry pushes.

**Artifact policy.** `.gitignore` encodes [[dec_01M0GH4HQA2F6NG4VTZ18YEHK1|Separate immutable sources, inferred semantics, and visual projections]] rather than describing it: weights and
checkpoint extensions, `.cache/`, `.work/`, `models/`, `corpus/generated/`, `corpus/derived/`,
`outputs/`, loose audio and video by extension anywhere in the tree, `*.timeline.json` with a
negation for test fixtures, `benchmarks/results/`, `.witnessglass/`, and
`.claude/settings.local.json`. `corpus/specs/` and `archaeology/` sit outside every ignored path
on purpose.

**Deviation from the sketched tree.** `.python-version` and `tests/conftest.py` were added;
`tests/__init__.py` was added so the CLI tests can import the contract fixtures. `uv.lock` is
committed and CI installs from it with `--locked`.
