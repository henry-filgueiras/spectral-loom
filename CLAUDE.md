# Working in this repository

Spectral Loom compiles music into a source-grounded semantic timeline and weaves that timeline
into synchronized visual projections. Read [README.md](README.md) for what exists, and
[docs/architecture.md](docs/architecture.md) for the invariants before changing anything
structural.

## Archaeology first

Project history lives in `archaeology/`, maintained with [Scarp](https://github.com/henry-filgueiras/scarp).
It is **tracked history, not disposable output**, and it is where the reasons live.

- **Consult it before any architectural decision.** `scarp list decisions`, `scarp list dragons`,
  `scarp list principles`. A decision already recorded is not re-litigated; it is either followed
  or superseded by a new decision that says so.
- **Update it when work changes the project's understanding** — a discovery, a constraint, a
  measurement that contradicts an assumption, a completed sprint. Not for routine work.
- **Use Scarp's own commands.** `scarp new <collection> "Title" --body-file …`,
  `scarp close <ref> --body-file …`, `scarp doctor`. Never hand-author a file under
  `archaeology/`, and never edit front matter, sequences, slugs, or paths — Scarp owns those.
  Scarp has no amend verb; if prose must be added to an existing artifact, that hand-edit is a
  deliberate act and must be noted as one.
- Record the honest version, including what failed and what remains unmeasured. An archaeology
  that only records successes is a marketing document.

## Truth layers never collapse

The single most important rule in this project. `requested`, `observed`, `inferred`, and
`corrected` are four different things and no code may flatten them into one.

- A prompt, a seed, a requested BPM: **requested**. Authored before the audio existed. Never
  presented as a fact about the audio. Specification fields carrying requests are named
  `requested_*`.
- A duration or a hash: **observed**.
- A model's output at an exact revision: **inferred**, with a confidence and an evidence link.
- A human override: **corrected**, recorded as its own provenance stage that leaves the inference
  it overrides intact.

A negative inference is not proof of absence. "No guitar events" means the analyser did not detect
a guitar, and code and projections must not render that as "there is no guitar".

See `archaeology/principles/0001`.

## Contracts and the compiler boundary

`song.timeline.json` is a language-neutral **file**, not an API. The renderer may end up in
another language and reads a versioned file; it never imports Python internals.

- The timeline carries musical observations. Never geometry, colour, shaders, camera behaviour,
  or any other rendering instruction.
- After changing `src/spectral_loom/contracts.py`, regenerate the schemas:
  `uv run python -m spectral_loom.schemas --write`. The drift test will catch it if you forget.
- A schema version bump is a code change to a `Literal` and a regenerated schema, because
  documents on disk outlive the code that wrote them. A field may gain meaning additively; it may
  never quietly change meaning under an unchanged version.
- Keep the event vocabulary open. New observation kinds are new namespaces, not schema changes.

## Artifacts

**Never commit**: model weights, checkpoints, Hugging Face caches, virtual environments, generated
audio, separated stems, timelines inferred during experimentation, rendered video, WitnessGlass
recordings, temporary audio, or benchmark output. `.gitignore` encodes this; do not weaken it, and
do not `git add -f` past it.

**Do commit**: source, tests, schemas, corpus specifications, prompts, small textual fixtures,
provenance manifests, archaeology, and documentation.

If a test needs audio-like input, synthesize a minimal WAV into pytest's `tmp_path` and let the
test framework delete it. There is a `tone_wav` fixture in `tests/conftest.py`. Do not add an
audio fixture to the tree.

The test suite is hermetic: it opens no network connection and needs no model weights.
`tests/netguard.py` enforces the first with an autouse fixture, and CI never selects the escape
markers. A test that needs weights is marked `needs_model`; a test that must reach out is marked
`needs_network`. Both are deselected by default, and neither runs in CI. Weights are a
precondition obtained by a bootstrap script, never something a test downloads. See
`archaeology/decisions/0007`.

Model assets are fetched only by scripts that pin exact revisions, verify before downloading, are
idempotent, record licenses, and do not execute remote code. See `scripts/README.md`.

## Working discipline

- **Inspect the working tree before and after edits.** `git status` first; know what was already
  there. Uncommitted work you did not create is someone else's, and it is preserved, not tidied.
- **Preserve unrelated work.** Do not reformat, rename, or "fix" files outside the change at hand.
- **Commit coherent completed slices automatically** — a vertical slice that builds, passes its
  tests, and makes sense on its own. Write why, not what.
- **Never push without an explicit instruction.** `git push` is Henry's call, always. Do not
  configure anything that pushes automatically.
- **Verify behaviour with tests**, not by reasoning about the code. A change without a test that
  would have failed before it is unverified.
- **Report assumptions and the evidence for them.** Say what was measured, what was read from
  documentation, and what is still a guess. "Should work" is not a result.

## Commands

`./loom` is the entry point. It routes each command to the environment that command needs —
`.venv` for the light ones, `.venv-cabinet` for anything that touches a model — and forwards
arguments untouched. **It routes; it never implements.** Behaviour that exists only in the wrapper
is a bug in the wrapper. `tests/test_loom.py` asserts that every `spectral-loom` subcommand is
reachable from it, so a new CLI command cannot be added and forgotten here.

```sh
uv sync                                        # environment, from the committed lockfile
./loom help                                    # everything below, with its environment
./loom doctor                                  # prerequisites and cabinet state; changes nothing
./loom check                                   # format, lint, types, tests, schema drift
./loom bootstrap env|assets|status             # establish the model cabinet; human-invoked
./loom smoke                                   # run each pinned model once
./loom generate corpus/specs/example.yaml      # one specimen; needs the cabinet
./loom compile sparse-funk-exposed-bass        # accepted separation -> song.timeline.json
./loom review-timeline sparse-funk-exposed-bass  # the Timeline Observatory, for gate 4
scarp doctor                                   # archaeology invariants
```

Anything without a wrapper is run directly and deliberately, e.g. `uv run pytest -k cabinet`. Do
not add a wrapper verb for every task; `./loom` covers this project's own surface, not `uv`'s.
