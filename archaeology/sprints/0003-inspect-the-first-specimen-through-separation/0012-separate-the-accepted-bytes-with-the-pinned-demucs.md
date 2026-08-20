---
id: tsk_01M0GPWWC74KNQF7YTCNJ5TYWS
sequence: 12
kind: task
status: closed
sprint: spr_01M0GPVMBCYCX68KZF76QFQ5QS
created: 2026-08-20
closed: 2026-08-20
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

## Result

Done. `spectral-loom separate SPECIMEN` exists, runs from the cabinet, and refuses a great deal.

### The refusals, in the order they fire

All before a weight is loaded, because a mismatch found after an eighty-megabyte load is the same
mismatch found for the price of reading a few files.

1. **Bytes nobody accepted.** The source is hashed and matched against a tracked `SpecimenReview` of
   *that hash*. Four separate refusals: nobody reviewed this specimen, somebody reviewed a different
   rendering of it, somebody reviewed these bytes and rejected them, the review is unreadable. The
   second one prints both hashes.
2. **A cabinet that is not stocked**, naming the bootstrap. Separation does not download.
3. **An unavailable backend.** There is no fall back. `--device cpu` is legitimate and explicit and
   reaches the invocation, the provenance, the cache key and the report; *ending up* on CPU is not.
4. **An output directory that is not a result for this request**, printing why it is not.

### Not a moving revision

`demucs.pretrained.get_model` calls `hf_hub_download` with no revision and resolves whatever `main`
points at today. The adapter loads the pinned snapshot from disk with
`demucs.hf.load_safetensors_model` and `demucs.apply.BagOfModels`, reading `htdemucs.yaml` — the
bag's own definition of itself — from the pinned weights and putting the whole definition in the
cache key rather than only the part this bag happens to use.

### One parameter is not upstream's default, deliberately

`shifts` stays at **0** where `apply_model`'s own default is 1. Upstream implements shifts by drawing
a time offset from the *unseeded global RNG* and averaging; the stems would not be reproducible from
the parameters the manifest records. Sprint 2 measured that generation is byte-reproducible on MPS,
and this keeps separation in the same condition. Everything else reproduces `demucs.api.Separator`
exactly, including the mean/std normalization, which materially changes the result and is therefore
recorded rather than inherited.

### What the manifest says, and what it refuses to say

`SeparationManifest`, versioned, with a generated schema. It carries the accepted source hash, the
review and generation-manifest hashes, the full separator identity split into code and weights
because upstream versions them separately, every material parameter, the actual backend, the start
time and elapsed time, and every output's path, hash, duration, rate, channels, peak and RMS —
measured **after** writing, so the numbers describe the bytes a person will hear rather than a
tensor that was quantized on the way out. Clipped and non-finite samples are counted rather than
rescaled away, because a silent gain change would corrupt every later comparison against the source.

A stem's name field is `model_output`, not `instrument`. A contract validator rejects a stem whose
name is not one of the separator's own outputs, and a test asserts the contract has no `accepted`,
`quality`, `verdict`, `rating` or `score` field — whether the separation is any good is gate 3 and
is answered by ears.

Reconstruction and residual are `diagnostics`, structurally separate from `stems`: arithmetic on the
outputs, carrying no model opinion, and explicitly not tracks.

### Cache and atomicity

The key covers the source hash, the code identity and its published digest, the weights revision,
the bag definition, every parameter, and the backend. Reuse re-hashes **every file the manifest
declares**, and misses with a stated reason when the key differs, an output is missing, an output
changed, the manifest is internally inconsistent, or the stems disagree about their sample rate —
because `docs/provenance.md` says a run that should have hit cache and did not is a bug report, and
a silent miss is the cheapest way to hide an unstable key.

The result is built in a per-process workspace beside its destination and promoted with one rename.
Anything already there is moved to `separation.superseded.N`, never deleted: unexpected bytes are
evidence about something, and the bootstrap already refuses to destroy them.

### Tests

25 hermetic tests over every pure decision, the refusals, the cache misses and the promotion, none
of which touch torch, weights or audio. One `needs_model` test runs the real thing end to end
against the real weights in a temporary repository, deselected by default and never in CI:

```sh
UV_PROJECT_ENVIRONMENT=.venv-cabinet \
    uv run --locked --extra cabinet --no-dev --with pytest pytest -m needs_model
```

`--with` layers pytest on for the run rather than installing it into an environment the bootstrap
deliberately builds `--no-dev`.
