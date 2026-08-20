---
id: tsk_01M0GH7R51C5GGAV6ZDN3P2SFF
sequence: 2
kind: task
status: pending
sprint: spr_01M0GH70AX635WAS8M3SQQRV9W
created: 2026-08-20
---

# Define the versioned song contracts and generate their schemas

## Objective

Define the two versioned contracts — `SongSpec` and `SongTimeline` — in Pydantic v2, generate
their JSON Schemas into `schemas/`, and make drift between the Python source and the committed
schemas a test failure.

## Acceptance criteria

- `SongSpec` carries a stable specimen id, generator adapter and model identity with a revision
  field that may be unresolved, prompt, seed, requested duration, and optional requested BPM,
  key/scale, time signature, and instruments — all request-labelled per principle:1 — plus a
  contained extension field for generator-specific parameters.
- `SongTimeline` carries a schema id and version, specimen id, source audio hash and duration,
  an explicit time unit, per-stage provenance, logical tracks, and generic timed events with
  type, start, optional end, optional confidence, evidence, and a namespaced payload.
- The event vocabulary is open; no chords, sections, lyrics, engraving, or rendering fields.
- `schemas/song-spec.schema.json` and `schemas/song-timeline.schema.json` are committed, and a
  test regenerates and compares them.
