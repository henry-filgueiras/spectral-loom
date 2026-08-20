---
id: tsk_01M0GK7KVSB4E0DX1BSBRZ7WWD
sequence: 5
kind: task
status: pending
sprint: spr_01M0GK725M1JMHQH8PQVSMGS7Q
created: 2026-08-20
---

# Resolve the cabinet into exact identities and lock them

## Objective

Resolve what this project actually means by "ACE-Step 1.5", "Demucs", and "Basic Pitch", from
authoritative upstream sources, and record it as a tracked artifact that survives a clean clone.

The unit being pinned is not "a model revision". Each entry has as many identities as upstream
gives it: the implementation that executes, the weights that are loaded, and the runtime whose
version materially changes what inference does. Where those are separate upstream, they are
separate here.

## Acceptance criteria

- For each of the three: upstream source, license, the exact implementation identity, the exact
  asset identity where assets are downloaded separately, and every hash upstream publishes.
- Immutable identities only — a commit sha, a repository revision, a released version with its
  distribution digest. No branches, no bare tags.
- `trust_remote_code` off. If a candidate checkpoint requires it, that candidate is rejected and
  the rejection is recorded with what was chosen instead.
- A tracked manifest, in a representation that fits these three systems rather than a general
  plugin format invented for them.
- The manifest is machine-readable, is parsed by the package rather than by a script, and is
  covered by hermetic tests.
