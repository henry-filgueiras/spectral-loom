---
id: dec_01M0GH551CZF4QBEVQZYB391XF
sequence: 5
kind: decision
status: accepted
created: 2026-08-20
---

# Keep heavyweight model dependencies out of the default environment

## Context

ACE-Step, Demucs, and Basic Pitch are the expected cabinet. They do not obviously co-exist: they
pin different numeric stacks, they disagree about torch, and one of them wants TensorFlow-family
runtime while another wants Torch. Resolving all three into the environment that also runs
`ruff` and `pytest` would make the fast feedback loop hostage to the slowest resolver in the
ecosystem, and would put multi-gigabyte wheels in the way of a contributor who only wants to run
the tests.

This round installs none of them, so the claim above is a stated expectation, not a measurement.

## Decision

The default environment carries the contracts and the CLI, and nothing that needs a GPU.

- Model integrations arrive as **optional dependency groups** (`[project.optional-dependencies]`)
  or, where the constraints genuinely cannot be reconciled, as **separately managed pinned
  environments** invoked as subprocesses across the file boundary that decision:3 already
  establishes.
- A stage that shells out to a foreign environment must still write the same provenance envelope,
  naming the environment it actually used.

Model assets are governed by a policy that is written now and implemented later. A future model
bootstrap script must:

- pin an exact repository revision or model commit, never a moving branch or a bare tag;
- be idempotent — running it twice does the work once;
- verify whether the pinned artifact is already present, by hash where a hash is published, and
  skip the download when it verifies;
- record the license and provenance of what it fetched;
- avoid executing arbitrary remote model code (`trust_remote_code` and its equivalents) without
  an explicit, reviewed, written reason.

## Consequences

- `uv sync` stays fast and a clean clone stays small.
- The CLI must treat a missing model dependency as **information**, not as a failure: `doctor`
  reports absence and exits zero. Bootstrap health and inference readiness are different
  questions and must not share an exit code.
- Cross-environment stages pay a subprocess and a serialization cost, which is accepted; the
  alternative is a single environment that cannot be resolved at all.
- No script implementing any of this exists yet. `scripts/README.md` states the contract so the
  first such script is reviewed against it rather than inventing its own rules.
