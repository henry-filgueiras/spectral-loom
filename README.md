# Spectral Loom

Spectral Loom compiles music into a source-grounded semantic timeline, then weaves that timeline
into synchronized analytical and artistic visual projections. The audio file is the evidence; a
`song.timeline.json` is a typed, versioned record of what was observed or inferred from it, with
the provenance of every producing stage attached; and a projection is a back end that reads that
record and draws from it. Prompts, seeds, and requested tempos describe what was *asked for* and
are never presented as facts about what the audio contains.

## Status: pre-alpha, and this repository contains no pipeline

**Nothing in the pipeline below is implemented.** This round produced the compiler boundary and
the paperwork around it: the data contracts, their generated JSON Schemas, an infrastructure-only
CLI, the artifact policy, CI, and the project archaeology. No model has been downloaded, no audio
has been generated, no stem has been separated, no timeline has been inferred, and no pixel has
been rendered.

## The pipeline this is built toward

```text
music generator
    → song audio
    → source separation
    → stem-specific analysis
    → song.timeline.json
    → deterministic visual projections
```

The expected initial model cabinet is ACE-Step 1.5 (generation), Demucs (separation), and Basic
Pitch (note inference). None of them is installed, and the architecture is arranged so any of the
three can be replaced without changing the boundary artifact.

## Setup

Requires [`uv`](https://docs.astral.sh/uv/). It fetches the pinned CPython 3.11 itself.

```sh
git clone git@github.com:henry-filgueiras/spectral-loom.git
cd spectral-loom
uv sync
```

## CLI

The `spectral-loom` command is infrastructure only. None of it downloads a model, generates
audio, infers a timeline, or renders anything.

```sh
uv run spectral-loom doctor                      # local prerequisites; changes nothing
uv run spectral-loom doctor --json               # same, machine-readable
uv run spectral-loom validate-spec corpus/specs/example.yaml
uv run spectral-loom validate-timeline path/to/song.timeline.json
```

`doctor` reports the OS and architecture, the Python version, the Apple chip and unified memory
on macOS, `ffmpeg` and `uv`, the repository path, and whether the cache and output locations are
writable. It also reports the future model packages as **absent**, which is the expected state:
bootstrap health and inference readiness are different questions and do not share an exit code.

Exit codes are part of the interface: `0` ok, `1` blocked, `2` invalid document, `3` unreadable
input.

## Tests, lint, and types

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv run python -m spectral_loom.schemas          # fails if the committed schemas drifted
```

Regenerate the schemas after any contract change with
`uv run python -m spectral_loom.schemas --write`.

## Artifact policy

**Tracked:** source, tests, schemas, corpus specifications, prompts, small textual fixtures,
provenance manifests, Scarp archaeology, documentation.

**Never tracked:** model weights, Hugging Face caches, virtual environments, generated songs,
separated stems, timelines inferred during experimentation, rendered video, WitnessGlass
recordings, temporary audio, and local benchmark results unless something is explicitly promoted
later. The ignored directories are `.work/`, `.cache/`, `models/`, `corpus/generated/`,
`corpus/derived/`, and `outputs/`; `corpus/specs/` and `archaeology/` are tracked and sit outside
them deliberately.

Expensive inference is cached independently of cheap rerendering, and every cache key includes
the input hashes, the model revision, and the parameters that mattered. See
[docs/architecture.md](docs/architecture.md).

## Out of scope

**There is no Spotify integration and no streaming-service capture in this project, now or
later.** Spectral Loom works on audio it generated from a specification it holds, or on audio a
user supplies deliberately. Also out of scope: live streaming, remote inference, accurate
engraved sheet music, generalized DAW functionality, a large UI, and cloud infrastructure. See
[docs/roadmap.md](docs/roadmap.md) for the full deferral list.

## Next experiment

Gate 1 of [the roadmap](docs/roadmap.md): pin the model cabinet. Resolve exact revisions for
ACE-Step 1.5, Demucs, and Basic Pitch, discover whether they co-exist in one Python environment
(`archaeology/dragons/0002` says they may not), and write the idempotent, revision-pinned
bootstrap script that `scripts/README.md` already specifies but does not yet contain.

Gate 2 is one 30–60 second instrumental specimen, generated and accepted by ear. No corpus is
generated before that.

## Project archaeology

Decisions, open dragons, principles, and sprint records live in `archaeology/`, maintained with
[Scarp](https://github.com/henry-filgueiras/scarp). Read `archaeology/decisions/` before making
an architectural change; it is tracked history, not disposable output.

## License

MIT. See [LICENSE](LICENSE).
