---
id: tsk_01M0GPWWCJ72WZPT95M103773B
sequence: 15
kind: task
status: closed
sprint: spr_01M0GPVMBCYCX68KZF76QFQ5QS
created: 2026-08-20
closed: 2026-08-20
---

# Watch the pinned cabinet stay remotely resolvable

## Objective

A pin establishes identity, not availability. Notice, on a schedule, when a pinned cabinet artifact
stops being resolvable — before a clean clone discovers it during a bootstrap.

## Acceptance criteria

- An explicitly networked script checks metadata only and downloads no weights.
- Per asset it distinguishes, as far as the provider actually establishes: repository reachable,
  pinned revision reachable, expected paths present, declared size and identity metadata still
  compatible, gated or authentication-required, transient provider failure, and unavailable for
  an unknown reason. An artifact is not called deleted unless the provider says so.
- Human-readable and `--json` output.
- A scheduled workflow, separate from hermetic PR CI, runs it roughly weekly with network
  explicitly permitted, downloads nothing, infers nothing, mutates nothing, and fails with a
  useful summary.
- No automatic cabinet update and no recovery mechanism. Choosing a replacement is a later,
  explicit experiment.
- Classification logic is tested hermetically against recorded provider responses.

## Result

Done. `uv run scripts/check_cabinet_remote.py [--json]`, plus a weekly workflow that is deliberately
not PR CI.

Metadata only — stdlib and `urllib`, no `huggingface_hub`, no weights, no inference, no writes, no
auto-update. It runs from the default environment because asking a repository whether it still
exists does not need eleven gigabytes of torch. A test greps the source for `hf_hub_download`,
`snapshot_download`, `resolve/` and `huggingface_hub` and fails if any appears.

**Every pin currently resolves**, first run, exit 0: `diffusers==0.40.0`, `demucs==4.1.0` and
`basic-pitch==0.4.0` against the digests PyPI publishes, and both weights repositories at their
pinned revisions with 21 and 5 files present — 7 of them verified against the sha256 the hub
publishes per LFS blob, the rest by size.

### The providers were measured, not assumed, and one of them surprised us

**The Hugging Face hub answers a request for a repository that does not exist with
`401 Invalid username or password` — the same answer it gives for a private repository you cannot
see.** It is refusing to distinguish "gone" from "not yours". So the sentinel refuses too: that case
is `authentication-required`, and a test asserts the finding never contains `deleted`, `removed` or
`no longer exists`, while it does contain *"This is NOT a statement that the artifact is gone"*.

A bad *revision* of a repository that does exist answers `404`, which is a genuinely different fact
and gets `revision-unresolvable` — a revision is immutable, so a 404 means history moved under the
pin, and the finding says that nothing here establishes which way. PyPI answers `404` for an unknown
distribution and for an unknown version of a known one alike, so it is asked twice and the two are
reported differently.

Seven verdicts: `available`, `revision-unresolvable`, `paths-missing`, `metadata-mismatch`,
`authentication-required`, `transient`, `unknown`. A newly gated repository reports `available` with
a note, because it still resolves and a fresh bootstrap would now need a token.

### Three exit codes, and the third one is the point

`0` every pin resolved · `1` a pin demonstrably did not · `2` a pin could not be confirmed either
way · `3` the manifest is unreadable. A monitor that returned "fine" because it could not reach the
network would be worse than no monitor, and one that returned "gone" for the same reason would be
worse still.

### Shape

`fetch` is the only impure function and never raises; classification is pure functions over recorded
`Probe`s, which is what lets 23 hermetic tests drive every verdict from real recorded response
shapes with `netguard` still armed.

`.github/workflows/cabinet-availability.yml` runs Mondays 06:17 UTC, `contents: read`, network
explicitly permitted, uploads the JSON on failure, and writes a step summary that repeats the
restraint rule. A test asserts from both sides that the two workflows stay separate: hermetic CI
contains no `bootstrap_cabinet.py`, `smoke_cabinet.py`, `check_cabinet_remote.py`, `--extra cabinet`,
`needs_model` or `needs_network` step, and the sentinel contains no fetch or model step.

`--unblock-me-please` was **not** implemented and the cabinet is never updated automatically.
Noticing and choosing are different problems and only the first one is cheap.
