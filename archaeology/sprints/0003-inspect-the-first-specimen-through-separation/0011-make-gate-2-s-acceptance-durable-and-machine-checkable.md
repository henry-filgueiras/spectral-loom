---
id: tsk_01M0GPWWC2KDKA2DRAD3XZF0JW
sequence: 11
kind: task
status: pending
sprint: spr_01M0GPVMBCYCX68KZF76QFQ5QS
created: 2026-08-20
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
