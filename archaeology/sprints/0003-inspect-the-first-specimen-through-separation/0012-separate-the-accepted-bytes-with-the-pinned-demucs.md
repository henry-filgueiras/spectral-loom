---
id: tsk_01M0GPWWC74KNQF7YTCNJ5TYWS
sequence: 12
kind: task
status: pending
sprint: spr_01M0GPVMBCYCX68KZF76QFQ5QS
created: 2026-08-20
---

# Separate the accepted bytes with the pinned Demucs

## Objective

Add the smallest real source-separation stage: the pinned Demucs implementation loading the
pinned HTDemucs snapshot, applied to bytes a human accepted, emitting attributable stems and a
versioned manifest.

## Acceptance criteria

- Requires the cabinet environment and refuses clearly outside it.
- Requires an accepted-specimen receipt, hashes the source before inference, and refuses when the
  hash differs from the accepted one — naming both hashes.
- Loads the pinned snapshot directly. `demucs.pretrained.get_model` and anything else that
  resolves a moving upstream revision is not on the path. Nothing downloads.
- The backend is explicit: the cabinet's declared accelerator by default, an unavailable one is a
  refusal rather than a fall back, and a CPU run is an explicit flag that appears in the
  invocation, the provenance, the cache key, and the report.
- A versioned separation manifest attributes the accepted source hash, the receipt and generation
  record, the Demucs distribution identity, the exact weights revision and model signature, every
  material parameter, the actual runtime and backend, the start time and elapsed time, and every
  output's path, hash, duration, sample rate and channel count — plus warnings and cache-key
  inputs. The producing stage is `inferred`; the measurements are `observed`. No human quality
  judgement appears in it.
- Stem names are recorded as the separator's own output names, never as verified instruments.
- The cache key covers the source hash, the code identity, the weight revision and signature, the
  parameters, and the backend. Reuse requires a matching key, every declared output present,
  every hash still matching, and internally consistent metadata; a partial or corrupt prior run
  is not a hit.
- Outputs are written to a temporary location and promoted atomically. Unexpected existing bytes
  are preserved or refused, never silently overwritten.
- Hermetic tests cover every pure decision and the manifest validation. Model-requiring tests are
  marked and stay out of CI.
