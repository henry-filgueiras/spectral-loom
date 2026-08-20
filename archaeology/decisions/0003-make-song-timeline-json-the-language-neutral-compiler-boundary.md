---
id: dec_01M0GH417X877T1W7PT99GVSNF
sequence: 3
kind: decision
status: accepted
created: 2026-08-20
---

# Make song.timeline.json the language-neutral compiler boundary

## Context

The analysis half of this project is Python, because that is where the models live. The rendering
half probably is not: deterministic, frame-accurate, GPU-resident visual projection is better
served by a shader pipeline or a native renderer than by a Python draw loop, and the renderer may
well be written in another language entirely.

If the renderer imported Python objects, that choice would be foreclosed today, silently, by an
import statement — and worse, a projection could then mutate the observations it was given.

## Decision

`song.timeline.json` is the compiler boundary, and it is a *file*, not an API.

- It is language-neutral JSON with an explicit schema id and version in its envelope.
- Everything downstream of analysis reads it. Nothing downstream imports Python internals.
- Its JSON Schema is generated from the Python contracts, committed, and drift-tested, so the
  file format is reviewable in the diff rather than implied by whatever Pydantic did this week.
- It carries musical observations only: events, times, confidences, and the provenance of the
  stage that produced them.

What it deliberately does not carry: geometry, colour, shaders, camera behaviour, layer order,
or any other rendering instruction. A field that tells a renderer what to draw does not belong in
the timeline even when it would be convenient.

## Consequences

- The renderer may be rewritten, or written in another language, without touching the analysis
  side. The contract that survives is a versioned file.
- Two projections of the same timeline — one analytical and debuggable, one artistic — are the
  same program run with different back ends, not two pipelines.
- The schema must be versioned honestly. An additive change bumps the version; a change in the
  meaning of an existing field is a new schema id, because a cached timeline on disk outlives
  the code that wrote it.
- The event vocabulary stays open. Early events are expected to be activity samples, activity
  intervals, and onsets; notes come later. Sections, chords, lyrics, and engraving are not
  modelled, and modelling them early would be inventing an ontology instead of observing one.
