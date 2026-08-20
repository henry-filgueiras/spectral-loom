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

One 45-second specimen exists for `sparse-funk-exposed-bass`, and **it has been heard.** Henry
listened on 2026-08-20 and accepted it, so gate 2 is passed — by a human, which is the only way
that gate can be passed. The acceptance is tracked even though the audio is not:
`corpus/reviews/sparse-funk-exposed-bass.8ff73623a29d.review.json` names the exact accepted bytes,
the reviewer, the date, and each criterion answer. What it accepts is narrow — *these bytes are
suitable as an experimental specimen* — and it establishes nothing about what the audio contains.

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

`./loom` is the entry point. There are two environments in this project and which one a command
needs is a fact about the command, so the router knows it and you do not:

```sh
./loom help
```

Everything below can also be run directly — `./loom` forwards arguments untouched and `exec`s, so
the exit code is the underlying command's. The direct form is shown where it is useful to know.

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
./loom bootstrap env       # the pinned environment, from the committed lockfile
./loom bootstrap assets    # the pinned weights
./loom smoke               # run each one once
```

Re-running `assets` downloads nothing: every pinned file is checked against the sha256 upstream
published before the hub client is even imported. See [scripts/README.md](scripts/README.md).

A pin establishes identity, not availability, so a separate weekly job asks whether the pinned
artifacts are still resolvable upstream — metadata only, no weights, no inference, no auto-update:

```sh
uv run scripts/check_cabinet_remote.py [--json]
```

It refuses to call an artifact deleted unless a provider actually says so, which the Hugging Face
hub notably does not: it answers a request for a nonexistent repository and for a private one
identically.

## CLI

```sh
./loom doctor                      # local prerequisites and cabinet state
./loom doctor --json               # same, machine-readable
./loom doctor --verify             # hash every pinned model file; still no download
./loom validate-spec corpus/specs/example.yaml
./loom validate-timeline path/to/song.timeline.json

./loom generate corpus/specs/example.yaml
./loom accept sparse-funk-exposed-bass --reviewer Henry --reviewed-on 2026-08-20 ...
./loom separate sparse-funk-exposed-bass
./loom review-separation sparse-funk-exposed-bass
```

`generate` is the only expensive command and the only one that needs the cabinet environment. It
never downloads; weights are a precondition the bootstrap establishes. It refuses to run against a
specification whose generator revision is null or disagrees with the cabinet, and an unchanged
request against an unchanged revision reuses the existing specimen rather than burning another
inference run.

`separate` runs the pinned HTDemucs snapshot over bytes a human accepted, and refuses everything
else. It hashes the source before loading a weight and requires a review of *that hash*; it loads
the snapshot from disk rather than through `demucs.pretrained.get_model`, which resolves whatever
`main` points at today; it downloads nothing; and it does not fall back between backends, because
the same weights on MPS and on CPU are not the same result — an unavailable backend is a refusal
and `--device cpu` is a deliberate choice that reaches the provenance, the cache key and the
report. Outputs land under `corpus/derived/<specimen>/separation/`, ignored, with a manifest that
attributes them. A second identical run is a cache hit only after every file that manifest declares
has been re-hashed, and an unexpected directory where the output goes stops the run rather than
being overwritten.

The stems are named `bass`, `drums`, `other`, `vocals` because **those are HTDemucs' own output
names**, not because anything verified what is in them. A near-silent `vocals.wav` is a failure to
assign, never proof that nobody sang.

`review-separation` builds the **Stem Observatory** and opens it: one local page in which the
source mix, every model output, and the engineering diagnostics share a single Web Audio transport
clock, so solo, mute, loop and A/B comparison mean something. Independently running `<audio>`
elements drift, and two lanes that drift are two lanes you cannot compare. Lanes are labelled
`HTDemucs · bass`, provenance sits behind a disclosure, and the residual is presented as a
diagnostic with a number rather than a verdict. It writes an ignored page under
`corpus/derived/<specimen>/review/`, serves it on loopback only from a fixed whitelist of files,
makes no request that leaves the machine, and records no verdict — gate 3 is passed by listening.

```text
space play/pause   0 source   1-4 solo one output   A all four outputs
M rendered sum     R residual   [ ] loop bounds     <- -> seek 5 s    esc clear
```

`accept` records what a person decided after listening. It runs no model and reads no audio beyond
hashing it, and the hash is the point: a specimen id names an *intent* and survives regeneration,
so a matching directory name is not evidence that anyone heard these particular bytes. The review
is written to `corpus/reviews/<specimen>.<hash>.review.json`, is tracked, carries every gate
criterion with the exact wording it was asked in, and can record a rejection as readily as an
acceptance. Downstream stages require a review of the hash they actually measured. See
[archaeology/decisions/0010](archaeology/decisions/0010-record-a-human-s-acceptance-as-a-hash-keyed-specimen-review-not-as-a-truth-layer.md).

`doctor` reports the OS and architecture, the Python version, the Apple chip and unified memory on
macOS, `ffmpeg` and `uv`, the repository path, whether the cache and output locations are
writable, and the state of every cabinet entry: pinned, installed, present, verified. An empty
cabinet is **information** and exits zero — bootstrap health and inference readiness are different
questions and do not share an exit code.

Exit codes are part of the interface: `0` ok, `1` blocked, `2` invalid document, `3` unreadable
input.

## Tests, lint, and types

```sh
./loom check
```

which is exactly this, in this order, stopping at the first failure:

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
provenance manifests, specimen reviews, Scarp archaeology, documentation. `model-cabinet.toml` is
the provenance manifest that must survive a clean clone, because it is the only record of which
code and which bytes produced anything here. A per-specimen `generation-manifest.json` travels with
its audio under `corpus/generated/` and is untracked with it — a record of a candidate nobody has
accepted is not history yet, and promoting one is a deliberate act. A `corpus/reviews/*.review.json`
is that deliberate act: it is what a human decided, it copies the observations and the provenance
it needs so it stands alone, and it is tracked precisely because the audio is not.

**Never tracked:** model weights, Hugging Face caches, virtual environments, generated songs,
separated stems, timelines inferred during experimentation, rendered video, WitnessGlass
recordings, temporary audio, and local benchmark results unless something is explicitly promoted
later. The ignored directories are `.work/`, `.cache/`, `models/`, `.venv-cabinet/`,
`corpus/generated/`, `corpus/derived/`, and `outputs/`; `corpus/specs/`, `corpus/reviews/`,
`model-cabinet.toml`, and `archaeology/` are tracked and sit outside them deliberately.

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

Gate 3 of [the roadmap](docs/roadmap.md): Demucs on the accepted specimen, with the stems listened
to. Like gate 2 it ends with a human, not with a program.

No corpus is generated before it passes.

## Project archaeology

Decisions, open dragons, principles, and sprint records live in `archaeology/`, maintained with
[Scarp](https://github.com/henry-filgueiras/scarp). Read `archaeology/decisions/` before making
an architectural change; it is tracked history, not disposable output.

## License

MIT. See [LICENSE](LICENSE).
