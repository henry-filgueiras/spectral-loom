---
id: tsk_01M0GV2MDTP1ZZFAM1KHQBZ2V1
sequence: 16
kind: task
status: closed
sprint: spr_01M0GV19568TPVR34C47C2NPVD
created: 2026-08-20
closed: 2026-08-20
---

# Bind Henry's gate 3 verdict to the exact separated bytes

## Objective

Bind Henry's gate 3 verdict to the exact separated bytes he heard, so that a clean clone knows gate
3 passed, and so that the compiler can require *those stems* rather than a directory that happens
to have the right name.

The stems stay untracked. The judgement about them does not.

## Acceptance criteria

- Before anything is recorded, the separation manifest and every artifact it declares are re-hashed
  and matched against the exhibit that was reviewed. A mismatch stops the round.
- A tracked, versioned document records: the accepted source hash, the gate 2 review's hash, the
  separation manifest's own content hash, the exact Demucs code and weights identity, every
  reviewed stem hash, the reconstruction and residual hashes that were part of the exhibit, the
  reviewer, the date, `accepted`, and every criterion in the wording it was asked.
- A separation whose hashes differ cannot inherit the acceptance, and the refusal names both
  hashes.
- The verdict preserves distinctions rather than flattening them: `other` stays `other`, no cymbal
  conclusion is drawn from material that was not clearly audible, and "no meaningful content was
  perceived in `vocals`" is not written down as "the source contained no vocals".
- The perceived level difference between the reconstruction and the source is preserved as a
  perceptual observation, not replaced by a signal metric.
- The supplementary second-listener assessment is recorded as context and is unmistakably
  subordinate to the named reviewer.
- A command writes it from the separation manifest plus the human's answers; it is not
  hand-authored, and it reuses the human-review primitive that already exists rather than inventing
  a review framework.
- README, roadmap, and archaeology say gate 3 is passed, with the evidence.

## Result

Done. **Gate 3 is passed**, and the record survives a clean clone even though the stems do not.

Everything the separation manifest declares was re-hashed before a word of the verdict was
written, and all seven artifacts matched: the source, the four model outputs, and the two rendered
diagnostics. The gate 2 receipt was re-hashed too and still matches what the separation ran
against. The verdict is therefore about the exact bytes Henry heard, and the round did not have to
transfer a review onto new bytes because a specimen id matched.

`corpus/reviews/sparse-funk-exposed-bass.3ccd7df63e7f.separation-review.json` is the receipt. It is
keyed by the separation manifest's own content hash —
`sha256:3ccd7df63e7f5209a9b20ea5765c5497ec2fa0aed9027540b7ee3221b449cf3f` — rather than by the
source hash, because one accepted recording can be separated many times and each of those is a
different set of bytes to have an opinion about.

### What the verdict says, and what it refuses to say

Bass clearly isolated with very little leakage. A possible slight kick-drum leak was heard, subtle
enough that it could equally have been a muted bass note, and the reviewer could not tell which —
so `bass-leakage-perceived` is `unclear`. That is what `unclear` is for, and resolving it by
guessing would have manufactured a finding out of an ambiguity. No bass material perceptibly
disappeared and nothing was objectionably smeared. Kick, snare/rimshot and hi-hat material is
coherent; no melodic leakage, no damaged transients. `other` is **not** a single-instrument stem.
`vocals` is perceptually silent. The reconstruction retains the source's character with no
objectionable artifacts.

Three of the answers are careful in a way that took more thought than the rest.

**No cymbal verdict exists, and the record says why.** The obvious sentence — "Demucs failed to
separate the cymbals" — is unavailable, because the accepted source did not offer clearly audible
cymbal or crash material to draw it from. The question is therefore worded as *was there enough
clearly audible cymbal material to judge cymbal separation at all*, answered `no`, with a note
saying explicitly that this is not a finding about the model. A question that presumes its own
answer is how an unanswerable question becomes a finding.

**A perceptually silent `vocals` is a failure to assign.** The question asks what was perceived *in
the `vocals` output*, never what the source contained. A test asserts the wording, because this is
the sentence most likely to drift.

**`other` keeps its name.** Multiple musical and timbral voices remain lumped together; the
reviewer suspects more than one guitar-like part and possibly a further synth-like timbre. Those
are recorded as suspicions in a note and are not instrument observations, and no criterion in the
set mentions an instrument name at all — asserted by a test, so that a later edit cannot invite the
rename by asking a leading question.

**The perceived level difference is preserved rather than corrected away.** Henry heard the
reconstruction as somewhat quieter than the original. The separation manifest already records
`reconstruction_rms` 0.113978 against `source_rms_at_model_rate` 0.114062, a difference of about
0.006 dB, which would have been an easy and wrong rebuttal: a signal metric answers a different
question than the one the reviewer was asked, and overwriting a perception with a number would
destroy the only data the gate produced.

### What exists that did not

A sixth contract, `SeparationReview`, with a generated schema, reusing the `HumanReview` and
`ReviewCriterion` primitives the contracts already had and inventing nothing else. Two review kinds
now exist and they justify reusing one primitive; they do not justify a framework. Thirteen gate 3
criteria, each stored with the exact wording it was asked in. One new command,
`accept-separation`, routed through `./loom`. A `SupplementaryListening` block, so the second
opinion Henry relayed is on the record as context without being mistaken for a second reviewer —
it names *how this project came by it*, because recording who said something without recording how
invites a later reader to assume it was an audition this project can vouch for.

Twenty-five new hermetic tests, several of them asserting question wordings rather than behaviour,
which is unusual and deliberate: in this document the wording *is* the behaviour.
