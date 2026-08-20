# Spectral Loom

Spectral Loom compiles music into a source-grounded semantic timeline, then weaves that timeline
into synchronized analytical and artistic visual projections. The audio file is the evidence; a
`song.timeline.json` is a typed, versioned record of what was observed or inferred from it, with
the provenance of every producing stage attached; and a projection is a back end that reads that
record and draws from it. Prompts, seeds, and requested tempos describe what was *asked for* and
are never presented as facts about what the audio contains.

## Status: pre-alpha, one arrow of the pipeline exists

The model cabinet is pinned and stocked, and a `SongSpec` becomes generated audio with a manifest
that makes it attributable. **Everything after that is unimplemented:** no stem has been
separated, no timeline has been inferred, and no pixel has been rendered.

One 45-second candidate exists for `sparse-funk-exposed-bass`. It has not been listened to, and
gate 2 is not passed by generating a file — it is passed by a human accepting one.

## The pipeline this is built toward

```text
music generator
    → song audio
    → source separation
    → stem-specific analysis
    → song.timeline.json
    → deterministic visual projections
```

The model cabinet is ACE-Step 1.5 (generation), Demucs (separation), and Basic Pitch (note
inference), pinned in [model-cabinet.toml](model-cabinet.toml). The architecture is arranged so
any of the three can be replaced without changing the boundary artifact.

## Setup

Requires [`uv`](https://docs.astral.sh/uv/). It fetches the pinned CPython 3.11 itself.

```sh
git clone git@github.com:henry-filgueiras/spectral-loom.git
cd spectral-loom
uv sync
```

That installs eighteen packages and no model. The cabinet is optional and lives in its own
environment; nothing below needs it except `generate`.

## The model cabinet

[model-cabinet.toml](model-cabinet.toml) is the tracked record of what this project means by
ACE-Step, Demucs, and Basic Pitch. The weights are untracked, so from a clean clone that file is
the only surviving statement of which code and which bytes produced any result here.

The unit of pinning is **not** "a model revision". Upstream versions code and weights separately,
so each entry records the implementation that executes, the assets it loads, and the runtime whose
version materially changes results. Basic Pitch has no assets at all: it ships its weights inside
its own wheel, so its distribution digest is the whole identity.

Stocking it is deliberate, human-invoked, and downloads about 11.2 GB:

```sh
uv run scripts/bootstrap_cabinet.py env                            # the pinned environment
.venv-cabinet/bin/python scripts/bootstrap_cabinet.py assets       # the pinned weights
.venv-cabinet/bin/python scripts/smoke_cabinet.py                  # run each one once
```

Re-running `assets` downloads nothing: every pinned file is checked against the sha256 upstream
published before the hub client is even imported. See [scripts/README.md](scripts/README.md).

## CLI

```sh
uv run spectral-loom doctor                      # local prerequisites and cabinet state
uv run spectral-loom doctor --json               # same, machine-readable
uv run spectral-loom doctor --verify             # hash every pinned model file; still no download
uv run spectral-loom validate-spec corpus/specs/example.yaml
uv run spectral-loom validate-timeline path/to/song.timeline.json

.venv-cabinet/bin/spectral-loom generate corpus/specs/example.yaml
```

`generate` is the only expensive command and the only one that needs the cabinet environment. It
never downloads; weights are a precondition the bootstrap establishes. It refuses to run against a
specification whose generator revision is null or disagrees with the cabinet, and an unchanged
request against an unchanged revision reuses the existing specimen rather than burning another
inference run.

`doctor` reports the OS and architecture, the Python version, the Apple chip and unified memory on
macOS, `ffmpeg` and `uv`, the repository path, whether the cache and output locations are
writable, and the state of every cabinet entry: pinned, installed, present, verified. An empty
cabinet is **information** and exits zero — bootstrap health and inference readiness are different
questions and do not share an exit code.

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
provenance manifests, Scarp archaeology, documentation. `model-cabinet.toml` is the provenance
manifest that must survive a clean clone, because it is the only record of which code and which
bytes produced anything here. A per-specimen `generation-manifest.json` travels with its audio
under `corpus/generated/` and is untracked with it — a record of a candidate nobody has accepted
is not history yet, and promoting one is a deliberate act.

**Never tracked:** model weights, Hugging Face caches, virtual environments, generated songs,
separated stems, timelines inferred during experimentation, rendered video, WitnessGlass
recordings, temporary audio, and local benchmark results unless something is explicitly promoted
later. The ignored directories are `.work/`, `.cache/`, `models/`, `.venv-cabinet/`,
`corpus/generated/`, `corpus/derived/`, and `outputs/`; `corpus/specs/`, `model-cabinet.toml`, and
`archaeology/` are tracked and sit outside them deliberately.

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

Gate 2 of [the roadmap](docs/roadmap.md), and it is not a coding task. One candidate exists and
nobody has heard it:

```sh
afplay corpus/generated/sparse-funk-exposed-bass/source.wav
```

The questions are the ones the specification's own notes ask: is the bass audible and exposed, is
there useful silence between phrases, are the parts separable by ear, and is there vocal bleed or
another generator failure that would make this a poor experimental specimen. A rejection is
recorded — including what was wrong — before the prompt is changed and another candidate is made.

Gate 3 is Demucs on the accepted specimen, with the stems listened to. No corpus is generated
before either.

## Project archaeology

Decisions, open dragons, principles, and sprint records live in `archaeology/`, maintained with
[Scarp](https://github.com/henry-filgueiras/scarp). Read `archaeology/decisions/` before making
an architectural change; it is tracked history, not disposable output.

## License

MIT. See [LICENSE](LICENSE).
