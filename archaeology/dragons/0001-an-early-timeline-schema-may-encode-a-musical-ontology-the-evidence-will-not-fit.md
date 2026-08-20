---
id: drg_01M0GH6ET52Y7VGZXY1BWEMJ6P
sequence: 1
kind: dragon
status: open
created: 2026-08-20
---

# An early timeline schema may encode a musical ontology the evidence will not fit

## Context

The timeline schema is being written before a single note has been analysed. Every field in it is
a guess about what musical observation looks like, made by someone who has not yet looked at a
Demucs stem or a Basic Pitch output.

Schemas fixed early are sticky: once a projection reads a field, changing that field's meaning
breaks something visible, and the pressure is then to bend observations to fit the schema rather
than the reverse.

## Question

How much musical ontology can be committed to now without encoding a wrong model of music that
later observations have to be distorted to fit?

## Constraints

- The event vocabulary is open (`type` is a string, payloads are namespaced), so adding an event
  kind is additive and cheap.
- The envelope is closed and versioned, so changing *it* is expensive and visible.
- Sheet-music engraving, chords, lyrics, sections, and any rendering instruction are explicitly
  not modelled — see decision:3.
- `song.timeline.json` files on disk outlive the code that wrote them, so a silent meaning change
  to an existing field corrupts data that already exists.

## Candidate direction

Keep the envelope thin and the events generic: type, start, optional end, optional confidence,
evidence, namespaced payload. Let the first three real event kinds — activity samples, activity
intervals, onsets — arrive from measurement rather than from design. Add notes only after a stem
has been inspected, and treat the first schema version as disposable until a real specimen has
passed through it end to end.

## Resolution criteria

Closed when a timeline compiled from a real separated specimen has been rendered by at least one
projection, and the envelope has survived that round trip without a field being reinterpreted.
If it did not survive, the resolution records which field was wrong and why.
