---
id: tsk_01M0HBNXMQ0WAW0TN6FNSR0V17
sequence: 25
kind: task
status: closed
sprint: spr_01M0GY4NYH1Q6R9HS0X7QKXSH4
created: 2026-08-20
closed: 2026-08-20
---

# Reconcile the seven provenance questions with what a timeline carries

## Objective

Reconcile `docs/provenance.md` with what a compiled timeline actually carries, and make the
reconciliation mechanical rather than prose.

## Acceptance criteria

- The seven questions are stated as they were; the document says precisely which of them the
  analysis stages answer in the timeline, which they do not, and where the rest are written down.
- The reason each omission exists is the reason it actually exists, including the one that buys a
  stronger property than the field it replaces.
- Tests assert the split rather than describing it, so the document cannot drift from the artifact
  again without something failing.
- No fixture answers fewer questions than real data does; a fixture that did would let a test pass
  against a document the pipeline never produces.
- The compiled timeline is byte-identical.

## Result

Done. This was a real contradiction and I introduced it in task 18.

`docs/provenance.md` opens with seven questions and the line *"An artifact whose provenance cannot
answer all seven is not evidence of anything. It is a file."* Checked against the artifact:

```
  stage                 Q1  Q2  Q3  Q4  Q5  Q6  Q7
  generate               ok  ok  ok  ok  ok  ok  ok
  separate               ok  ok  ok  ok  ok  ok  ok
  activity.measure       ok  ok  ok  --  --  --  ok
  activity.interval      ok  ok  ok  --  --  --  ok
  onset.spectral_flux    ok  ok  ok  --  --  --  ok
```

The project's own discipline was indicting its newest artifact, and nothing said why.

### The omissions are a trade, and one of them buys more than it costs

**Q4 and Q5.** `started_at` and `duration_ms` are exactly the fields that make a document differ
between two runs of identical inputs, and gate 4 requires the opposite. That much was already in the
module docstring.

What was *not* written down anywhere is the better half of the argument. `runtime` is stable within
a machine, so determinism alone did not require dropping it — dropping it means two people on
different machines compiling the same accepted stems with the same parameters get **byte-identical
documents**. A timeline becomes a function of its inputs rather than of who ran it, and can be
verified by recomputation instead of by trust. That is worth more than knowing which laptop was
warm, and it is the actual reason.

**Q6 has no answer at that level at all**, which is different from being omitted. An analysis stage
emits no file — it emits events *into* the document — and a document cannot carry its own hash.

All three answers exist in the build receipt, along with the timeline's sha256, the cache key, and
both human verdicts that had to match before the compile was allowed to start.

### Made mechanical

Four tests now assert the split instead of the prose describing it: every stage answers 1, 2, 3 and
7 in the document; the analysis stages carry no clock and no output hashes; the copied `generate`
and `separate` stages still answer all seven, so the exception did not widen; and the receipt
carries what the document does not, including both review hashes.

### One fixture was lying

`test_review.py`'s generation manifest had `runtime` but no `duration_ms` — it answered six of
seven where the real one answers all seven, and the new test caught it immediately. A fixture that
answers fewer questions than real data lets a test pass against a document the pipeline never
produces, which is worse than no test. Fixed to mirror the real manifest.

The compiled timeline is byte-identical:
`sha256:47e0178cc5b940c4545104c6c4eedb73b5f04d044f4e00b22dce23a583c977c4`.
