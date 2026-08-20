---
id: spr_01M0GH70AX635WAS8M3SQQRV9W
sequence: 1
kind: sprint
status: active
created: 2026-08-20
---

# Bootstrap the loom

## Goal

Stand up the Spectral Loom repository as a working, tested, honest skeleton: the compiler
boundary defined as versioned contracts with generated schemas, an infrastructure-only CLI, CI
that runs from a committed lockfile, the artifact policy encoded rather than described, and the
architecture and roadmap written down as evidence gates.

No model is downloaded, no audio is generated, no inference adapter is written, and no pixel is
rendered in this sprint.

## Rationale

Every later round in this project is expensive and irreversible in the way that model rounds are
expensive: multi-gigabyte downloads, long runs, and outputs whose correctness can only be judged
by listening. Doing that work against a repository with no contracts, no provenance envelope, and
no artifact policy would produce results nobody could later attribute to an input.

The cheap work is therefore the work that constrains the expensive work: what a timeline is, what
a provenance record must answer, what is tracked and what is not, and what counts as evidence
that a stage did its job. Bootstrapping is the round where those are free to change.

## Success criteria

- A public GitHub repository exists with `origin` configured and nothing pushed.
- `uv sync --locked` reproduces the environment from a committed lockfile on Python 3.11.
- `SongSpec` and `SongTimeline` exist as versioned Pydantic v2 contracts, small on purpose.
- JSON Schemas for both are committed and a test fails if they drift from the Python source.
- `spectral-loom doctor`, `validate-spec`, and `validate-timeline` work, with stable nonzero exit
  codes and useful human-readable errors; `doctor --json` is machine-readable.
- A missing future model dependency is reported by `doctor` as informational, not as failure.
- The example corpus specification validates; a synthesized timeline fixture validates; malformed
  contracts fail with errors that name the offending field.
- Ruff, mypy, and pytest pass locally and in CI.
- README, architecture, provenance, and roadmap documents exist and claim nothing that does not
  exist yet.
- The repository is armed for WitnessGlass without vendoring it and without committing recordings.

## Non-goals

- Any model download, weight, or checkpoint.
- Any generated audio, separated stem, or inferred timeline produced by a real model.
- Any inference adapter for ACE-Step, Demucs, or Basic Pitch.
- Any visual projection, renderer, or shader.
- Settling the musical ontology — see dragon:1.
- Pushing commits.
