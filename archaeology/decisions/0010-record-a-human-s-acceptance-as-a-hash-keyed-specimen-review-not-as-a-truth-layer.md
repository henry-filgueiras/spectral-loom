---
id: dec_01M0GQ8E8JAAAWT7A322SRKKTD
sequence: 10
kind: decision
status: accepted
created: 2026-08-20
---

# Record a human's acceptance as a hash-keyed specimen review, not as a truth layer

## Context

Gate 2 of `docs/roadmap.md` is passed by a human listening to a generated candidate and accepting
it. Henry did that on 2026-08-20 for `sparse-funk-exposed-bass`. The problem is where that fact
goes.

The audio is untracked by policy: it is bulky and regenerable from a pinned specification plus a
pinned revision. Its `generation-manifest.json` is untracked with it, deliberately — sprint 1
decided that "a record of a candidate nobody has accepted is not history yet". So after the
acceptance, the only durable statement in the repository still said the candidate was unheard, and
the only place the acceptance existed was a conversation.

Two further pressures shaped the answer.

**A specimen id is not a rendering.** `sparse-funk-exposed-bass` names an *intent* and survives
regeneration on purpose. Change the prompt, regenerate, and the same id and the same directory
path resolve to audio nobody has heard. Any downstream stage that gates on "has this been
accepted" by looking at a directory name is one prompt edit away from silently running on
unexamined bytes.

**A human judgement is not one of the four truth layers.** `archaeology/principles/0001` defines
`requested`, `observed`, `inferred`, `corrected`, and they classify claims about a *recording* by
where the claim came from. `corrected` is specifically a human override of an inference. An
acceptance overrides nothing and is not a claim about the recording at all.

## Decision

A **`SpecimenReview`** is a fourth versioned contract, tracked under `corpus/reviews/`, recording
one human's verdict on one exact rendering.

1. **It is keyed by the audio hash, not by the specimen id.** The filename is
   `<specimen-id>.<first-12-hex>.review.json`, and the document carries the full hash. Two
   renderings of one specimen are two files. `review.require_accepted(root, specimen_id, hash)`
   compares hashes and, when they differ, reports both — so a stage cannot accidentally satisfy
   its precondition with a matching directory name.

2. **The human judgement is not a truth layer and not a `Provenance` entry.** It lives in a
   `HumanReview` block of its own. A provenance entry exists so a stage's output can be attributed
   and recomputed; a review emits no artifact, cannot be recomputed, and giving a person a
   `tool_revision` would be a fiction. What the review records is what a named person perceived on
   a named day, and the field descriptions say exactly that: `bass-audible-and-exposed: yes` means
   the reviewer heard something they call an exposed bass, and establishes nothing about what the
   file contains.

3. **The observations are copied, not re-derived.** `source_audio`, `spec_hash` and the whole
   generation `provenance` list are copied verbatim from the generation manifest, so the accepted
   bytes remain attributable from a clean clone where that untracked manifest is absent. The
   manifest's own hash and `model-cabinet.toml`'s hash are recorded too, so a later divergence is
   visible rather than silent.

4. **The question set is fixed per gate, and travels with the answers.** The four gate 2 criteria
   are `corpus/specs/example.yaml`'s own notes. Each written answer carries the question's exact
   wording, so editing the constant later cannot retroactively change what an existing review
   claims. Every criterion must be answered; `unclear` exists so a reviewer who could not tell is
   not forced to say "no".

5. **Rejections are recorded in the same shape.** `accepted: false` plus what was wrong. A record
   that can only say yes is a marketing document.

6. **The `accept` command binds; it does not judge.** It re-hashes the audio rather than believing
   the manifest, refuses when the two disagree, and refuses to overwrite an existing review of the
   same bytes without `--force`.

## Consequences

The tracked surface grows by one directory and one schema. `corpus/reviews/` sits outside
`corpus/generated/` and `corpus/derived/`, beside `corpus/specs/`, which is the existing split
between what a human authored and what a model produced.

Gate 3 and everything after it now have a mechanical precondition instead of a social one:
`separate` will not load a weight until `require_accepted` returns. The cost is that regenerating
a specimen invalidates its acceptance, which is the intended cost — the new bytes have not been
heard.

The four truth layers are unchanged. This decision does not add a fifth; it says that a claim
about *fitness for a purpose* is outside the taxonomy, which classifies claims about audio. If a
later stage wants to record a human's claim about musical *content*, that is `corrected`, it
belongs in a timeline, and it is a different problem.

### What was rejected, and why

**Promote the generation manifest into the tree.** Cheapest, and wrong twice: it carries no
reviewer, no date and no criteria, and promoting it would make "a file exists" indistinguishable
from "a person listened", which is the exact conflation gate 2 exists to prevent.

**Record the acceptance in the Scarp sprint prose only.** Archaeology is where reasons live, and
it is genuinely durable — but it is not machine-readable, so `separate` could not require it, and
the check would be back to trusting a directory name.

**Give the review a `Provenance` entry at `truth_layer: corrected`.** Tempting, because it would
have reused the existing envelope, and `corrected` is the only one of the four layers whose author
is a person. Rejected because it is a category error in two directions at once: it would invent a
`tool_revision` for a human, and it would file a fitness judgement in a taxonomy about audio
content — quietly widening `corrected` from "a human overrode this inference" to "a human said
something", which is exactly the kind of drift principle 1 is written to prevent.

**Store one review per specimen id.** Would have made the lookup a one-liner, and would have meant
that regenerating a specimen either overwrote a recorded human judgement or left a document
silently describing bytes that no longer exist.
