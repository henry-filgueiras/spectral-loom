---
id: spr_01M0GH70AX635WAS8M3SQQRV9W
sequence: 1
kind: sprint
status: closed
created: 2026-08-20
closed: 2026-08-20
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

## Retrospective (2026-08-20)

Every success criterion met. Four tasks closed, one log filed, six decisions, one principle, and
two open dragons.

**What exists.** A public repository with `origin` configured and nothing pushed. A Python 3.11
environment reproducible from a committed `uv.lock`. `SongSpec` and `SongTimeline` as versioned
Pydantic v2 contracts with committed, drift-tested JSON Schemas. An infrastructure-only CLI whose
exit codes are part of its interface. CI running lint, strict types, tests, and the schema drift
check from the lockfile. Architecture, provenance, and roadmap documents. WitnessGlass arming that
vendors nothing.

**What deliberately does not exist.** No model, no weights, no audio, no stems, no inferred
timeline, no adapter, no renderer, and no plugin system waiting for its first plugin. The seams
that exist — the timeline file, the provenance envelope, the cache key — are the ones the pipeline
cannot work without.

**What the round changed about the plan.** Two things.

PyYAML moved from optional to a direct dependency, because corpus specifications are hand-authored
and are therefore YAML, which puts the parser on the default validation path rather than behind an
extra.

More usefully: the round produced a *shape* for the invariants that was not obvious when they were
written as prose. "Requested is not observed" became a test asserting that `SongSpec` has no field
named `bpm`; "the timeline carries no rendering instructions" became a test asserting that no
timeline model has a `camera` or `shader` field and that one smuggled into the envelope is
rejected at parse time. An invariant that only a document asserts is a hope.

**What is unmeasured, stated so a later round does not mistake it for settled.**

- **CI has never run.** It passes locally, command for command, but nothing has been pushed, so
  the workflow has not executed on GitHub once. `astral-sh/setup-uv@v5` and the Ubuntu runner are
  documentation-derived, not observed.
- **WitnessGlass hooks have never fired here.** The binary, the configuration, and the recordings
  directory are verified; that Claude fires the configured hooks in *this* repository can only be
  observed from the next session. See [[log_01M0GJ17Y731YQVJPA497NPGTB|Bootstrapping Spectral Loom: what the host lacked and how the recorder was armed]].
- **The model cabinet is untouched.** [[drg_01M0GH6ETFHGC354FJPB7ENSP1|The model cabinet may not resolve into a single Python environment]] asserts the three models may not co-exist in
  one environment and is open precisely because nobody has tried.
- **The timeline schema has never met a real specimen.** [[drg_01M0GH6ET52Y7VGZXY1BWEMJ6P|An early timeline schema may encode a musical ontology the evidence will not fit]] is the honest statement of
  that: version 0.1.0 was written before anyone looked at a Demucs stem, and it should be treated
  as disposable until a real specimen has passed through it end to end.

**Next.** Gate 1 of `docs/roadmap.md`: resolve exact revisions for ACE-Step 1.5, Demucs, and Basic
Pitch, find out which of them share an environment, and write the bootstrap script to the contract
already stated in `scripts/README.md`. Then one specimen, judged by ear, before anything is
generated in bulk.
