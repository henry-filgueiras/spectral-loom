# scripts/

**This directory is intentionally empty of scripts.** It exists to define a boundary, and to
state the contract that the first script placed here must satisfy — so that it is reviewed
against a written standard rather than inventing its own.

## What belongs here

Operational scripts that fetch, pin, or verify **model assets**: the bootstrap for ACE-Step 1.5,
Demucs, and Basic Pitch, and any later addition to the model cabinet.

## What does not

Anything that belongs in the package. The CLI lives in `src/spectral_loom/cli.py` and is the place
for anything a user runs as part of the pipeline. A script here is machine setup, not a pipeline
stage.

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

## Why they do not exist yet

Gate 1 of [../docs/roadmap.md](../docs/roadmap.md). Writing a bootstrap script before the
revisions are resolved would mean pinning nothing, which is the one thing the contract above
forbids.
