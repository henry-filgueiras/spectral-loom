---
id: dec_01M0GMW29G5CT0BH6B2ZYQKBME
sequence: 8
kind: decision
status: accepted
created: 2026-08-20
---

# Run ACE-Step through diffusers rather than trusting remote model code

## Context

`scripts/README.md` rule 5 and decision:5 both forbid executing arbitrary remote model code:
`trust_remote_code` and its equivalents stay off unless a written, reviewed reason says otherwise
for a specific model at a specific revision. Both were written before anyone had looked at an
ACE-Step checkpoint.

Looking at them, the rule turns out to be load-bearing immediately. Every ACE-Step 1.5 checkpoint
published in transformers layout is tagged `custom_code` on the Hugging Face hub and ships
`configuration_acestep_v15.py` and `modeling_acestep_v15_turbo.py` alongside its weights:
`ACE-Step/Ace-Step1.5`, `acestep-v15-base`, `acestep-v15-sft`, `acestep-v15-xl-turbo`,
`acestep-v15-xl-sft`, `acestep-v15-xl-base`, and the three `turbo-shift*` variants. Loading any of
them through `transformers` or `diffusers` auto-classes means `trust_remote_code=True`, which
means this project executes Python fetched from a model host at import time.

There is a second path. The ACE-Step team contributed the pipeline upstream into `diffusers`,
where it is `diffusers.AceStepPipeline` — real, reviewed, released library code — and published
three checkpoints in diffusers layout to go with it: `acestep-v15-xl-base-diffusers`,
`acestep-v15-xl-sft-diffusers`, and `acestep-v15-xl-turbo-diffusers`. Those repositories contain
no `.py` at all.

## Decision

**ACE-Step 1.5 enters the cabinet as `diffusers.AceStepPipeline` at a pinned diffusers version,
loading `ACE-Step/acestep-v15-xl-turbo-diffusers` at a pinned revision. Every `custom_code`
ACE-Step checkpoint is rejected, and `trust_remote_code` stays off.**

What follows from taking the rule seriously rather than going around it:

- The choice of checkpoint is constrained by the rule, not by quality. Only the XL variants have
  diffusers-format publications, so the smaller `acestep-v15-turbo` is unavailable to this project
  even though it would download faster. 11.1 GB is the price of not running remote code.
- The implementation and the weights have **separate identities**, because upstream versions them
  separately. `model-cabinet.toml` records both. There is no single "ACE-Step revision" and
  inventing one would name a thing that does not exist.
- The LM planner (`acestep-5Hz-lm-*`) is not in the cabinet. The diffusers pipeline wraps the DiT
  half only, and that is the half this project wants: a planner that rewrites the prompt into a
  song blueprint would insert an unrecorded inference between the request and the audio, which
  principle:1 exists to prevent.
- A future ACE-Step release that ships only in transformers layout does not silently arrive. It is
  a new decision, and this one is what it would have to supersede.

## Consequences

Three alternatives were available and each was rejected for a reason worth keeping.

**Turn on `trust_remote_code` for one pinned revision.** The rule explicitly allows this with a
written reason, and the revision *is* pinned, so the code that would execute is fixed and
auditable. Rejected because a cheaper path exists that needs no exception at all, and an exception
granted when it was not needed is the one that gets cited next time it is.

**Vendor the upstream `acestep` package from `ace-step/ACE-Step-1.5` at a commit sha.** This is
running the same code, with the review burden moved onto this project and the update path made
manual. It also does not remove the `custom_code` load: the checkpoints still carry their own
modeling files.

**Use `ACE-Step/ACE-Step-v1-3.5B`,** the previous generation, which is in diffusers layout without
custom code. Rejected: it is a different, older model, and choosing it would be choosing worse
music to avoid a problem that the 1.5 diffusers repositories already solve.
