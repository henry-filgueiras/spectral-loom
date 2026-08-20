---
id: dec_01M0GH4HQA2F6NG4VTZ18YEHK1
sequence: 4
kind: decision
status: accepted
created: 2026-08-20
---

# Separate immutable sources, inferred semantics, and visual projections

## Context

Three kinds of artifact pass through this pipeline and they have nothing in common except that
they all end up as files on a disk:

- a **source** artifact is evidence — a specification someone wrote, or an audio file that exists
  and can be listened to;
- an **inferred** artifact is a model's opinion about a source, expensive to produce, cheap to
  be wrong about, and only meaningful alongside the model revision that produced it;
- a **projection** is a rendering of an inference, cheap to redo, and worthless as evidence.

Collapsing them into one `output/` directory is the normal thing to do and it destroys the only
property that makes the pipeline auditable: knowing which files are allowed to disagree with the
audio, and which are not.

## Decision

The three layers are separated by directory, by cache policy, and by what Git tracks.

**Immutable / source** — tracked. Song specifications, prompts, small textual fixtures, schemas,
provenance manifests, documentation, archaeology, and code. Audio itself is *source* but is not
tracked: it is bulky and regenerable from a pinned specification plus a pinned model revision.

**Inferred semantic** — untracked, cached, and keyed. Stems, timelines, note inferences. Every
cache key includes the input hashes, the model or tool identity, its exact revision, and the
parameters that mattered. A cache entry whose key cannot be recomputed is garbage, not a cache.

**Projections** — untracked and disposable. Rendered frames and videos are rebuilt from a
timeline whenever they are wanted.

Ignored directories: `.work/`, `.cache/`, `models/`, `corpus/generated/`, `corpus/derived/`,
`outputs/`. Tracked corpus specifications live at `corpus/specs/` and are deliberately outside
the ignored `corpus/` subtrees.

## Consequences

- Expensive inference is cached independently of cheap rerendering. Changing a colour must never
  re-run Demucs.
- A clean clone contains no audio, no weights, and no timelines, and can still run its tests —
  which forces test fixtures to be small, textual, or synthesized in a temporary directory.
- Promoting an inferred artifact to tracked evidence (a benchmark result worth keeping, a
  human-corrected timeline) is an explicit act with a provenance record, not a stray `git add`.
- Witnessglass recordings are runtime output of the observing tool, are not redacted, and are
  never committed.
