---
id: log_01M0GJ17Y731YQVJPA497NPGTB
sequence: 1
kind: log
created: 2026-08-20
---

# Bootstrapping Spectral Loom: what the host lacked and how the recorder was armed

Findings from the bootstrap round that are not decisions and not task results: things that were
measured, things that turned out differently than expected, and things a later round should not
have to rediscover.

## The host did not have the toolchain the project assumes

`git` 2.53.0, `gh` 2.96.0, and `ffmpeg` 8.1 were present. **`uv` and Python 3.11 were not.** The
system interpreter is 3.14.6, there was no `python3.11` on `PATH`, and Homebrew had no
`python@3.11` installed.

Both were installed during this round: `uv` 0.12.5 from Homebrew, and CPython 3.11.16 by
`uv python install 3.11` — which is the reason `uv` is the only prerequisite a contributor needs.
This is recorded because [[dec_01M0GH3HAHBCYE2HE8MGDEKWS0|Build on Python 3.11 with uv as the environment authority]] reads as though it ratified an existing environment. It
did not; the environment was built to match the decision, and a machine that already had a 3.11
would have hidden that.

## The arming mechanism is not the one the README documents

WitnessGlass's README documents `./scripts/arm.sh`, and that script is the **wrong tool for an
external project**: it resolves `ROOT` to its own checkout, and the committed hook example names
the binary through `${CLAUDE_PROJECT_DIR}/target/debug/witnessglass`, which inside this repository
points at a path that does not exist. Running it here would have armed WitnessGlass, not
Spectral Loom.

The mechanism that applies is in that project's `archaeology/logs/0001`, which records a previous
external commissioning and, in its addendum, the measurement that matters: Claude's exec form
resolves a bare `command` on `PATH` on macOS. Idea 7 upstream — *arm and disarm a repository that
is not this one* — is still parked, so hand-authoring the configuration is the current documented
path, not a workaround around a tool that exists.

What was done here, in order:

1. `cargo install --path ~/witnessglass --locked --force`, built with `CARGO_TARGET_DIR` pointed
   at a scratch directory so that `~/witnessglass` was not written to at all. It ends the round
   with a clean tree at `050fea4`. The previously installed binary predated eleven commits;
   re-installing was not optional, since `arm.sh` exists partly to stop a stale binary from
   quietly recording a real session using old code.
2. `arm.sh`'s three gates, re-run by hand against a synthetic `SessionStart` payload: exit 0,
   **zero bytes on stdout** (Claude reads a hook's stdout as a decision, so a chatty recorder is a
   recorder that interferes), and a recording written. `replay` round-tripped it.
3. `.claude/settings.local.json` written from the upstream example with the command rewritten to
   the bare `witnessglass` exec form and the recordings directory pointed at
   `${CLAUDE_PROJECT_DIR}/.witnessglass/recordings`. All eight hook surfaces.
4. End-to-end check into the real repository-local recordings directory, verified with
   `check-recording.sh` — which validates without printing the recording — then the synthetic
   recording was deleted.

**What is verified and what is not.** Verified: the binary works, the recordings directory is
writable, the configuration is valid JSON with eight surfaces, and a hook invocation with the
exact configured arguments produces a complete recording. Not verified: that Claude actually
fires these hooks in *this* repository, because that cannot be observed from inside the session
that armed it. The first recording will appear in `.witnessglass/recordings/` on the next
session; if it does not, `PATH` resolution from Claude's exec form is the first thing to suspect.

**This session is not recorded.** Arming takes effect on the next session, and arming mid-session
produces a partial recording with no session start. Accepted rather than worked around.

## Scarp refused a dangling reference, and was right to

`scarp close task:4 --body-file …` was rejected with `artifact-not-found` because the narrative
cited `[[log:1]]` before this log existed. The write was refused whole rather than landing
half-bound — the artifact stayed `pending` rather than closing with a broken citation in it. The
fix was to write the log first and close the task afterwards, which is also the more honest
ordering.

## Implementation findings worth keeping

- **PyYAML became a direct dependency, not an optional one.** The brief allowed it "only if
  needed for corpus specifications", and it is: specifications are hand-authored and are therefore
  YAML, so the parser sits on the default validation path. Timelines stay JSON — they are
  machine-written, and a machine has no reason to want YAML.
- **`Literal` schema versions cost four mypy errors and were worth it.** Module constants typed
  as plain `str` cannot be assigned as defaults to `Literal` fields; annotating them `Final` fixes
  it and makes the constant and the field the same type by construction.
- **Pydantic's `JsonValue` renders as an empty JSON Schema definition.** The extension bags —
  `generator_params`, `parameters`, `payload` — are therefore `object` with unconstrained values.
  That is accurate rather than lazy: those vocabularies belong to the generator and the analysis
  tool, not to this project, and constraining them here would be inventing a schema for someone
  else's data.
- **Two contract invariants are enforced in the model rather than left to convention**: an event
  citing an evidence stage absent from the document's own provenance is rejected, and duplicate
  stage names or track ids are rejected because both are cache-key inputs.
- **The tests that matter are property tests, not example tests.** That `SongSpec` has no field
  named `bpm`, that no timeline model carries a `camera` or `shader` field, that a rendering field
  smuggled into the envelope is rejected, and that `doctor` creates nothing in a directory it
  probes — each of those would have caught a real future mistake, which is more than a round-trip
  test does.

## Measured on the bootstrap host

`doctor` reports Apple M5 Pro (18 cores), 24 GiB unified memory, macOS 26.4.1 on arm64,
Python 3.11.16, `uv` 0.12.5, ffmpeg 8.1, and four absent model packages — `torch`, `demucs`,
`basic_pitch`, `acestep` — exiting 0. Fifteen checks, none blocking.

**No model was downloaded, no audio was generated, and nothing was pushed.**
