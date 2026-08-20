---
id: tsk_01M0GK89WR1EE5H17W3AJP7PFJ
sequence: 8
kind: task
status: closed
sprint: spr_01M0GK725M1JMHQH8PQVSMGS7Q
created: 2026-08-20
closed: 2026-08-20
---

# Execute each pinned model once and record what backend it used

## Objective

Execute each pinned cabinet entry once on this machine, to establish the only claim a smoke can
support: this exact thing runs here, in this environment, on this backend.

A smoke is not an evidence gate. It does not say the separation is good or the notes are right;
gates 3 and 5 do that, with a human listening.

## Acceptance criteria

- Each of the three runs real inference once, on input small enough to be synthesized locally
  where that is sufficient to exercise the model.
- Recorded per model: the device actually selected, the package and runtime versions in play,
  success or failure, any warning that changes what the result means, and enough of the output's
  shape to show inference occurred rather than an object being constructed.
- Runtime output stays untracked unless something small and textual is deliberately promoted.
- Gate 1 either passes or has a precise recorded blocker. A blocker is not resolved by swapping
  a model without discussion.

## Result

Done. **Gate 1 passes.** `scripts/smoke_cabinet.py` runs each entry against a synthesized
two-channel input — a bass tone, a lead tone, and a periodic transient, because a separator handed
silence returns silence and looks like it worked.

Host: Apple M5 Pro, 18 cores, 24 GiB unified memory, macOS 26.4.1, CPython 3.11.16, torch 2.13.0,
MPS available and built, CUDA absent.

| entry | executed | backend | evidence that inference happened |
| --- | --- | --- | --- |
| basic-pitch | yes, 3.9 s | CoreML `nmp.mlpackage` | 6 note events; first at MIDI 40 — E2 — which is the 82.4 Hz tone in the input |
| demucs | yes, 3.4 s | MPS | `[1, 4, 2, 88200]`, all finite, sources `drums bass other vocals`, model rate 44100 |
| ace-step | yes, 8.9 s after a 7.3 s load | MPS (`mps:0`, bfloat16) | `[2, 480000]` at 48 kHz — ten seconds of stereo — finite, peak 0.891, RMS 0.213 |

**Nothing fell back to CPU, and nothing claimed acceleration it did not deliver.** That was the
question worth asking, because a silent CPU fallback produces perfectly good-looking output and
nothing downstream would notice.

Basic Pitch's backend is the one worth restating: it is not on MPS and cannot be, because it is not
a Torch model in this environment. It ships four serializations and picks one at import time from
whichever runtime is importable — TF, then CoreML, then TFLite, then ONNX. On macOS at Python 3.11
its own markers install coremltools and nothing else, so CoreML wins by default rather than by
choice, and the selected serialization is part of what produced any note. Recorded in the manifest
for that reason.

**Warnings that were checked and judged.** coremltools 9.0 warns on import that scikit-learn 1.9.0
is unsupported and torch 2.13.0 untested; both concern its conversion API, which this project never
uses, so both are noise — accurate noise about how far from tested ground that corner sits, which
is in [[drg_01M0J0K6BJ5G4G3EVXDG8SR1MJ]]. ACE-Step logs "Guidance scale 7.0 is ignored for turbo
(guidance-distilled) checkpoints", which is upstream confirming that the `guidance_scale` the
example specification used to carry would have been a parameter in the cache key that changed
nothing. torch warns that `weight_norm` is deprecated; cosmetic.

**One failure, kept as evidence rather than smoothed over.** The first Basic Pitch smoke did not
run at all: `ModuleNotFoundError: No module named 'pkg_resources'`, three levels down a chain no
resolver could see. That is the whole reason this task exists as something separate from "the
environment resolved". Full account in [[drg_01M0GH6ETFHGC354FJPB7ENSP1]].

**What a smoke is not.** It says these pinned things execute here, on these backends. It says
nothing about whether the separation is clean or the note is right — those are gates 3 and 5, and
they are judged by a human listening. The per-source RMS in the demucs report is a shape check, not
a quality measurement; the input was two sine waves.
