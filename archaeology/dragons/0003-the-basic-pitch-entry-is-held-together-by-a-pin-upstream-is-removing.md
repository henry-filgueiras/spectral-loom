---
id: drg_01M0GMX88A5CNXJ1DF8RHZQHZH
sequence: 3
kind: dragon
status: open
created: 2026-08-20
---

# The Basic Pitch entry is held together by a pin upstream is removing

## Context

Basic Pitch is in the cabinet at 0.4.0, and getting it to execute took a pin that exists for no
reason a reader would guess:

```
basic-pitch 0.4.0  requires  resampy<0.4.3
resampy 0.4.2      does      `import pkg_resources` at module import time
pkg_resources      shipped with setuptools and was REMOVED in setuptools 81
```

The environment resolved. The environment installed. `import basic_pitch` succeeded. Then
`import basic_pitch.inference` raised `ModuleNotFoundError: No module named 'pkg_resources'`,
because nothing in the dependency graph declares setuptools and modern setuptools no longer
carries the module resampy reaches for. `setuptools==80.9.0` — the last release that still ships
`pkg_resources` — is in the cabinet extra solely to keep a transitive import alive.

resampy fixed this in 0.4.3 by moving to `importlib.resources`. basic-pitch's cap is what keeps
the fix out of reach, and basic-pitch's last release was 0.4.0.

Two further facts about the same entry, recorded because they compound:

- On macOS with Python 3.11, basic-pitch's own environment markers install **coremltools and
  nothing else**, so the CoreML `.mlpackage` is what executes. Which of its four bundled
  serializations runs is decided at import time by whichever backend package happens to be
  importable — a property of the resolved environment, not of anything this project asked for.
- coremltools 9.0 warns on import that scikit-learn 1.9.0 is unsupported (max tested 1.5.1) and
  that torch 2.13.0 is untested (max tested 2.7.0). Both warnings are about coremltools'
  *conversion* API, which this project never uses, so they are noise today. They are also an
  accurate signal that this corner of the environment is further from tested ground than the rest
  of it.

## Question

How long can Basic Pitch stay in this cabinet, and what is the cost of the day it cannot?

Concretely: what breaks first — setuptools dropping the 80.x line from an index, a security fix
this project needs in a package that conflicts with the pin, or something in the coremltools /
scikit-learn / torch triangle that stops merely warning and starts failing? And when it does, is
the answer a fork, a vendored resampy shim, a different note-inference model, or dropping notes
from the pipeline entirely?

## Constraints

- Gate 5 of the roadmap already treats notes as **optional**: a timeline without notes stays valid
  and a failing note stage degrades the timeline rather than failing the compile. So this dragon
  threatens a feature, not the pipeline.
- `scripts/README.md` and decision:8 rule out the shortcut of vendoring or patching upstream code
  into the tree without a written reason.
- Nothing here is urgent. It executes today, on CoreML, and produced correct pitches for a
  synthesized test tone.

## Candidate direction

Do nothing until gate 5, which is where a note stage is actually written. Then measure Basic
Pitch against real bass stems and decide whether it earns the maintenance it costs. If it does not,
the optionality gate 5 already requires is the exit: notes stop being emitted and the timeline
stays valid.

Watch for the pin becoming impossible rather than merely ugly — that is the signal to act early.

## Resolution criteria

Closed when either Basic Pitch has produced note events from a real separated stem that a human
judged useful, and the setuptools pin has been re-examined against whatever the environment looks
like then — or when note inference has been removed from the cabinet with the reason recorded.
