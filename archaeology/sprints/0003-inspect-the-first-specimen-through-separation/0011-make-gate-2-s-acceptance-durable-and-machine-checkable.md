---
id: tsk_01M0GPWWC2KDKA2DRAD3XZF0JW
sequence: 11
kind: task
status: closed
sprint: spr_01M0GPVMBCYCX68KZF76QFQ5QS
created: 2026-08-20
closed: 2026-08-20
---

# Make gate 2's acceptance durable and machine-checkable

## Objective

Turn Henry's listening into a tracked artifact that names the exact bytes he heard, so that a
clean clone knows gate 2 passed and so that separation can require the accepted hash instead of
trusting a directory name.

The audio stays untracked. The judgement about it does not.

## Acceptance criteria

- A new versioned contract with a generated JSON Schema records one human review of one exact
  rendering: schema identity, specimen id, accepted source sha256, observed duration, sample
  rate and channels, the specification's content hash, the generator and cabinet identity that
  produced the bytes, enough provenance to attribute them, the reviewer, the review date, each
  criterion and its response, and an unambiguous `accepted` flag.
- The document can record a rejection as well as an acceptance, and a rejection carries what was
  wrong.
- Nothing the prompt requested — tempo, key, instrument — appears anywhere in the document as a
  fact about the audio. A test asserts it.
- The receipt is keyed by the audio hash, not only by the specimen id, so two renderings of the
  same specimen cannot be confused for one another.
- A command writes it from the generation manifest plus the human's answers; it is not
  hand-authored.
- README, roadmap, and archaeology say gate 2 is passed, with the evidence.

## Result

Done. **Gate 2 is passed**, durably, and the record survives a clean clone even though the audio
does not.

```
corpus/reviews/sparse-funk-exposed-bass.8ff73623a29d.review.json     (tracked)
  reviewer     Henry
  reviewed_on  2026-08-20
  accepted     true
  source       sha256:8ff73623a29d213b0732296c5dfbff1aa8908fc2a78647b14ed754209b9aa628
  observed     45.00 s · 48000 Hz · 2 ch
  spec_hash    sha256:26e16131…6125a
  cabinet_hash sha256:621986da…3f2c
  bass-audible-and-exposed        yes
  useful-silence-between-phrases  yes   "drums remain continuous, other instruments leave space"
  parts-separable-by-ear          yes
  generator-failure-perceived     no    "no vocal bleed and no other obvious generator failure"
```

The local `source.wav` was hashed before anything else this round and matched the hash Henry named,
exactly. Nothing proceeded on the assumption that it would.

### The shape, and why it is that shape

`SpecimenReview` is a fourth versioned contract with a generated schema. Three choices in it are
load-bearing and are argued in [[dcn_01M0KDMDVCJPSBVBSD3AC8MSVN]]:

**Keyed by the audio hash, not the specimen id.** The file is
`<specimen>.<first-12-hex>.review.json` and the document carries the full digest.
`require_accepted(root, id, hash)` compares hashes and, when they differ, prints both. A specimen id
names an *intent* and survives regeneration on purpose, so gating on it would have been one prompt
edit away from silently separating audio nobody had heard.

**The human judgement is not a truth layer and not a `Provenance` entry.** It lives in its own
`HumanReview` block. A provenance entry exists so a stage can be attributed and recomputed; a review
emits no artifact, cannot be recomputed, and giving a person a `tool_revision` would be a fiction.
Filing it under `corrected` would have quietly widened that layer from "a human overrode this
inference" to "a human said something".

**The observations are copied, not re-derived**, along with the whole generation provenance, so the
accepted bytes stay attributable from a clean clone where the untracked generation manifest is
absent. The manifest's own hash and `model-cabinet.toml`'s are recorded so a later divergence is
visible.

### What acceptance does and does not mean

Written into every gate 2 review as a `purpose` field, so it cannot be quietly widened:

> These exact bytes are suitable as this project's first experimental specimen. This is not a claim
> that any requested instrument, tempo, or key was objectively established.

A test serializes a review with the generation provenance removed — the one place a prompt is
allowed to be, because that stage is labelled `requested` — and asserts that `96`, `D minor`,
`electric bass` and `close-miked` appear nowhere in what is left.

Rejections are the same document with `accepted: false` and what was wrong. `unclear` is a legal
answer, because failing to perceive something is not establishing its absence.

### Also

`accept` binds; it does not judge. It re-hashes the audio rather than believing the manifest,
refuses when the two disagree, refuses to overwrite a recorded judgement without `--force`, and
requires every criterion to be answered. `spectral_loom.hashing` now holds the digest helpers that
three modules had started to want.
