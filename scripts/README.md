# scripts/

**This directory holds only operational model-asset scripts.** It exists to define a boundary,
and it states the contract every script placed here must satisfy — so that each is reviewed
against a written standard rather than inventing its own.

## What belongs here

Operational scripts that fetch, pin, or verify **model assets**: the bootstrap for ACE-Step 1.5,
Demucs, and Basic Pitch, and any later addition to the model cabinet.

## What does not

Anything that belongs in the package. The CLI lives in `src/spectral_loom/cli.py` and is the place
for anything a user runs as part of the pipeline. A script here is machine setup, not a pipeline
stage.

Also not here: `../loom`, the router that gives both halves one entry point. It sits at the
repository root because a wrapper you have to type a directory name to reach has not saved anyone
anything, and because it is neither machine setup nor a pipeline stage — it knows which environment
each command needs and nothing else.

## The contract for a model bootstrap script

Every script in this directory must:

1. **Pin an exact revision.** A commit sha for a repository, a commit or immutable revision id for
   a model. Never a branch. Never a bare tag — tags move, and a tag that moved after a result was
   recorded silently invalidates that result with no diff anywhere.
2. **Be idempotent.** Running it twice does the work once. Running it on a half-finished download
   finishes it rather than corrupting it.
3. **Verify before fetching.** Check whether the pinned artifact is already present, by published
   hash where a hash is published, by revision id otherwise, and **skip the download when it
   verifies**. Bandwidth is the least of it: a re-download that silently produces different bytes
   is the failure this rule exists to catch.
4. **Record license and provenance** into a tracked manifest. The weights are untracked, so this
   record is the only thing that survives a clean clone, and "which license was this under" is not
   a question to answer from memory.
5. **Not execute arbitrary remote model code.** `trust_remote_code` and its equivalents stay off.
   Turning it on for a specific model at a specific revision requires a written, reviewed reason
   recorded in `archaeology/decisions/`.
6. **Write into ignored locations only** — `models/`, `.cache/`, `.work/` — and never into a
   tracked path.
7. **Be invoked by a human, never by a test or by CI.** The test suite is hermetic and downloads
   nothing; weights are a precondition a script here establishes deliberately, and a test that
   depends on them is marked `needs_model`. See `../archaeology/decisions/0007-keep-the-test-suite-hermetic-no-network-no-model-weights.md`.

## Why they did not exist at first

Gate 1 of [../docs/roadmap.md](../docs/roadmap.md). Writing a bootstrap script before the
revisions are resolved would mean pinning nothing, which is the one thing the contract above
forbids. The revisions were resolved in sprint 2 and are in
[../model-cabinet.toml](../model-cabinet.toml).

## What is here now

Two scripts, both human-invoked, neither reachable from a test or from CI.

### `bootstrap_cabinet.py`

Establishes the cabinet described by `../model-cabinet.toml`.

```sh
uv run scripts/bootstrap_cabinet.py env       # build the pinned environment
.venv-cabinet/bin/python scripts/bootstrap_cabinet.py assets   # fetch the pinned weights
uv run scripts/bootstrap_cabinet.py status    # report; changes nothing
```

`env` materializes the `cabinet` extra into `.venv-cabinet/` from the committed
lockfile rather than into `.venv/`, so stocking the cabinet does not destroy the
environment that runs `ruff` and `pytest`. `assets` needs `huggingface_hub` and
therefore runs from that environment.

Against the contract above, point by point:

1. Revisions come from the manifest, whose contract rejects anything that is not
   forty hex digits. No flag accepts a branch.
2. and 3. Every pinned file is checked against the size and the sha256 upstream
   published **before** the hub client is imported; an asset that verifies is
   skipped without a network call. Partial downloads are resumed rather than
   restarted, and files that do not match what is pinned stop the fetch instead
   of being overwritten.
4. License and provenance live in `../model-cabinet.toml`, which is tracked. The
   untracked `.spectral-loom-fetched.json` beside the weights is a local receipt,
   not the record.
5. `trust_remote_code` appears nowhere, and every pinned repository contains no
   `.py` at all. The one pickle in the ACE-Step repository is listed as excluded
   and is never fetched.
6. Everything written lands under `models/` or `.venv-cabinet/`.
7. The decisions the script makes live in `spectral_loom.cabinet` and are tested
   there, hermetically. The script itself is never executed by the suite.

**Idempotency is demonstrated, not asserted.** `--offline` verifies and refuses
to download, so after a successful run it must succeed and report every asset
skipped:

```sh
.venv-cabinet/bin/python scripts/bootstrap_cabinet.py assets --offline
```

### `smoke_cabinet.py`

Runs each pinned entry once against synthesized input and reports the device,
the backend, the versions, and the shape of what came back.

```sh
.venv-cabinet/bin/python scripts/smoke_cabinet.py [entry ...] [--json]
```

It exists because "the recipe was installed and run once" is what gate 1 of
[../docs/roadmap.md](../docs/roadmap.md) asks for, and because a backend that
silently falls back to CPU produces output that looks perfectly fine. **A smoke
is not an evidence gate.** It says the pinned thing executes here. It says
nothing about whether a separation is clean or a note is right; those are gates
3 and 5, and they are judged by listening.

### `check_cabinet_remote.py`

Asks whether every pinned artifact is still resolvable upstream. **Metadata only:
no weight is downloaded, no model is loaded, nothing on disk is touched.**

```sh
uv run scripts/check_cabinet_remote.py [--json] [--timeout SECONDS]
```

It exists because a pin establishes *identity*, not *availability*.
`../model-cabinet.toml` says exactly which bytes this project means by "Demucs";
it cannot make anyone keep serving them. The failure it catches is the quiet
one — a repository goes private, a version is deleted from an index — and the
cost of catching it late is a clean clone that cannot be bootstrapped.

This is the **only** script here that reaches the network as its purpose, and it
runs from the default environment on stdlib and `urllib`. It has its own
scheduled workflow, `.github/workflows/cabinet-availability.yml`, deliberately
separate from the hermetic PR CI so that nobody has to wonder which rules apply
to which file.

**A provider's silence is not a death certificate**, and the verdicts are shaped
around what the hosts actually say. Measured while the script was written:

- the Hugging Face hub answers a request for a repository that does not exist
  with `401 Invalid username or password` — the *same* answer it gives for a
  private repository you cannot see. It is refusing to distinguish "gone" from
  "not yours", so the script reports `authentication-required` and refuses too;
- a bad *revision* of a repository that does exist answers `404`, which is a
  genuinely different fact and gets a different verdict;
- PyPI answers `404` for an unknown distribution and for an unknown version of a
  known one alike, so the two are separated by asking twice.

Exit codes are the scheduled job's whole interface, and the third one is the
point: a monitor that returned "fine" because it could not reach the network
would be worse than no monitor, and one that returned "gone" for the same reason
would be worse still.

| code | meaning |
| --- | --- |
| 0 | every pin resolved |
| 1 | a pin demonstrably did not resolve |
| 2 | a pin could not be confirmed either way |
| 3 | the cabinet manifest is unreadable |

**It repairs nothing and updates nothing.** Choosing a replacement for an
artifact that has become unavailable is a decision with its own evidence, and it
belongs in `../archaeology/decisions/`.
