---
id: dec_01M0GJF3V698EM8Y8GHYKM4JB8
sequence: 7
kind: decision
status: accepted
created: 2026-08-20
---

# Keep the test suite hermetic: no network, no model weights

## Context

decision:5 keeps heavyweight model dependencies out of the default environment, and
`scripts/README.md` states the contract a future model bootstrap must satisfy. Neither says
anything about the **test suite**, and neither is enforced by anything that runs.

That gap is the easy one to fall into. The first analyser stage that wraps Demucs or Basic Pitch
will want a test, the shortest path to that test is to let the library resolve its own default
checkpoint, and the library will happily download it. Nothing in the repository today would
notice. The cost lands later and lands on everyone: a unit suite that needs gigabytes on a cold
clone, a CI job whose green depends on a model host staying up and a cache staying warm, and a
failure mode where the suite passes on the machine that already has the weights and fails
everywhere else.

The current CI workflow does not download models, but only because no code exists yet that could.
That is an accident of timing, not an invariant, and the comment at the top of `ci.yml` asserting
it was unbacked.

## Decision

**The default test suite is hermetic: it opens no network connection and requires no model weights
on disk.** `uv run pytest` means the same thing on a cold clone, in CI, and on a machine with an
empty model cabinet.

This is enforced, not merely documented:

- `tests/netguard.py` installs an autouse fixture that raises `NetworkAccessError` on any socket
  connection leaving the machine. Loopback and Unix sockets stay open — a test that starts a local
  listener is doing something local. A test that reaches for a model host fails immediately, with
  a message naming this decision.
- Two markers are registered and **deselected by the default pytest options**: `needs_model` for a
  test that requires weights on disk, `needs_network` for a test that must reach out.
  `needs_network` is also the only way past the socket guard. Selecting either takes an explicit
  `-m`, which no CI step performs.
- The `Tests` step in CI runs with `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, and
  `HF_DATASETS_OFFLINE` set, so a hub client that somehow gets a chance fails at the client rather
  than pulling gigabytes into the runner.
- `tests/test_hermetic.py` asserts all of it, including that the guard genuinely blocks an
  outbound connection that succeeds without it.

Weights are a **precondition** of a model-dependent test, never something the test acquires.
A stage that needs weights obtains them through a bootstrap script satisfying the
`scripts/README.md` contract, run deliberately by a human, and its tests are marked `needs_model`
and skipped when the weights are absent.

Integration tests that exercise real models are expected, and they are welcome — under a marker,
on a machine where the cabinet is stocked, and never in the verification job that gates a pull
request. If that ever needs to change, it needs a decision superseding this one, not a quiet
addition to `ci.yml`.

## Consequences

- CI stays fast, offline, and independent of any model host's uptime. A red build means this
  repository is wrong.
- A test that quietly downloads a checkpoint cannot be merged by accident; it fails in the author's
  own run, at the connection, with the reason attached.
- Model-dependent verification does not happen automatically anywhere. That coverage is real and
  this decision does not provide it — a future decision has to say where those tests run and who
  looks at the result. Until then, "the suite is green" is a claim about the contracts and the
  CLI, not about any model integration.
- The guard blocks sockets, not filesystem reads. A test that loads weights already present in
  `~/.cache` without touching the network would pass on the author's machine and fail in CI on the
  `needs_model` path being absent — the marker is what prevents that, and the marker is a habit,
  not a mechanism. This is the residual weakness and it is accepted for now.
