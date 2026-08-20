---
id: tsk_01M0GK7KVSB4E0DX1BSBRZ7WWD
sequence: 5
kind: task
status: closed
sprint: spr_01M0GK725M1JMHQH8PQVSMGS7Q
created: 2026-08-20
closed: 2026-08-20
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

## Result

Done, and the shape of the answer was the finding.

**"A model revision" is not a unit.** Each of the three turned out to have a different number of
identities, and flattening them would have invented revisions that do not exist:

- **ACE-Step** has two. The implementation is `diffusers==0.40.0`, which carries
  `diffusers.AceStepPipeline` — contributed upstream by the ACE-Step team, so this is not a
  third-party reimplementation. The weights are `ACE-Step/acestep-v15-xl-turbo-diffusers` at
  `200ba991ae448051e14b0183157e35c2d27c9fb0`, MIT, 11.1 GB across 21 files, of which every
  `.safetensors` carries a sha256 published by the hub. There is no version string that covers
  both, and the manifest does not pretend there is.
- **Demucs** has two. `demucs==4.1.0` (MIT) and `adefossez/HTDemucs` at
  `bf35a81b663819a8255c8fefee17f9d812b786b5` (MIT), a bag of one model, signature `955717e8`,
  84 MB with a published sha256.
- **Basic Pitch has one, and that is a fact about upstream rather than a gap.** `basic-pitch==0.4.0`
  ships the ICASSP 2022 model *inside the wheel*, in four serializations — TensorFlow SavedModel,
  CoreML `.mlpackage`, ONNX, TFLite. There is nothing to download and nothing under `models/` for
  it. The distribution's sha256 is the complete identity of both the code and the weights.

**The `trust_remote_code` rule bit immediately.** Every ACE-Step 1.5 checkpoint in transformers
layout is tagged `custom_code` and ships its own `modeling_*.py`. Loading one requires
`trust_remote_code=True`, which `scripts/README.md` forbids. The diffusers-format repositories
contain no `.py` at all, which is why they are what got pinned — and it constrains the choice:
only the XL variants have diffusers publications, so the smaller `acestep-v15-turbo` is
unavailable to this project. 11.1 GB is what not running remote code costs here. See
[[dec_01M0HZS9V5F1AJ3RNZ8C3MEXBF]].

**Representation.** `model-cabinet.toml` at the repository root, beside `uv.lock`, because it is
the same kind of artifact: a lock over things fetched from the network. TOML because `tomllib` is
stdlib on 3.11, so `spectral_loom.cabinet` parses it with no dependency and `doctor` can read the
cabinet from an environment that contains none of it. Not a plugin format: three entries with
heterogeneous identity shapes, described as they actually are.

**Two things the manifest records that were nearly missed.**

`ACE-Step/acestep-v15-xl-turbo-diffusers` contains one pickle, `silence_latent.pt`. The pipeline
does not load it — the `silence_latent` it uses is a registered buffer inside the condition
encoder's safetensors — so it is listed as `excluded` and never fetched. No pickle from a model
host lands under `models/` in this repository, and a test asserts it.

`demucs.pretrained.get_model('htdemucs')` calls `hf_hub_download` with **no revision**, so it
resolves whatever `main` points at today. It is therefore unusable by this project as written. The
adapter loads the pinned snapshot through `demucs.hf.load_safetensors_model` and
`demucs.apply.BagOfModels` instead, which is what `get_hf_model` does anyway minus the unpinned
download. Recorded in the manifest because it is a constraint upstream imposes, not a preference.

**Tested hermetically**, 30 tests in `tests/test_cabinet.py`: that every revision is forty hex
digits, that an uppercase spelling of the same sha is rejected, that every entry records a license,
that every `.safetensors` carries an upstream hash, that no asset would fetch a `.py` or a pickle,
and that a typo in a pinned field fails loudly rather than being dropped.
