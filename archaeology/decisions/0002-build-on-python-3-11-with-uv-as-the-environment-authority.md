---
id: dec_01M0GH3HAHBCYE2HE8MGDEKWS0
sequence: 2
kind: decision
status: accepted
created: 2026-08-20
---

# Build on Python 3.11 with uv as the environment authority

## Context

The model cabinet this project expects to use is Python-first: ACE-Step, Demucs, and Basic Pitch
all publish Python entry points, and the audio analysis ecosystem around them (librosa, soundfile,
numpy) is Python as well. The host is Apple silicon macOS, where the accelerated backends differ
by model and where a wrong interpreter is a day lost.

Python 3.11 rather than a newer interpreter is chosen for a specific reason: the machine-learning
ecosystem lags the interpreter release train, and the three named models publish wheels and pins
against 3.10-3.11 far more reliably than against the current release. This is a compatibility
choice, not a preference, and it is expected to be revisited when the model cabinet is pinned.

`uv` rather than pip/venv/conda is chosen for lockfile determinism. Provenance is the whole point
of this project, and a provenance record that cannot name the exact environment that produced an
artifact is decoration.

## Decision

- Python 3.11 is the interpreter. `.python-version` pins it and `requires-python` enforces it.
- `uv` owns the environment, the dependency resolution, and `uv.lock`, which is committed.
- CI installs from the committed lockfile with `uv sync --locked`, so a drifted lockfile fails
  the build instead of being silently repaired.
- The default dependency set stays small enough to resolve in seconds: pydantic, and the dev
  group (pytest, ruff, mypy). No torch, no MLX, no model packages.

## Consequences

- Heavyweight model dependencies must arrive as optional dependency groups or as separately
  managed pinned environments, because their transitive constraints are expected to conflict
  with each other. Recorded separately as its own decision.
- A contributor needs `uv` and nothing else; `uv` fetches the interpreter itself.
- Neither `uv` nor Python 3.11 was present on the bootstrap host. Both were installed during
  this round: `uv` from Homebrew, and CPython 3.11 by `uv python install 3.11`.
