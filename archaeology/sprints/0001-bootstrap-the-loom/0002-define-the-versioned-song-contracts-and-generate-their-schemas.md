---
id: tsk_01M0GH7R51C5GGAV6ZDN3P2SFF
sequence: 2
kind: task
status: closed
sprint: spr_01M0GH70AX635WAS8M3SQQRV9W
created: 2026-08-20
closed: 2026-08-20
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

## Result

Done. Both contracts are Pydantic v2 with `extra="forbid"`, and both stamp their own
`schema_id` and `schema_version`.

**The version is a `Literal`, not a string.** Bumping it is a code change with a reviewable diff
and a regenerated schema, which is what [[dec_01M0GH417X877T1W7PT99GVSNF|Make song.timeline.json the language-neutral compiler boundary]] wants; a plain `str` would let a document
claim a version nobody implemented.

**Two invariants are enforced in the model rather than left to convention.** An event whose
`evidence.stage` does not name a stage present in the timeline's `provenance` is rejected —
grounding is checked, not merely encouraged. Duplicate stage names and duplicate track ids are
rejected, because both are cache-key inputs and a duplicate makes attribution ambiguous.

**Naming carries [[prn_01M0GH5QAPD237HP9NV9B8AXM8|Requested, observed, inferred, and corrected are different truth layers]].** A test asserts that `SongSpec` has no field named `bpm`,
`key`, `duration_s`, `tempo`, `instruments`, or `time_signature`: an unlabelled musical field on
a specification asserts an observation the specification cannot have made. A second test asserts
that no timeline model carries a `color`, `shader`, `geometry`, `camera`, `layer`, `opacity`, or
`focus` field, and a third that such a field smuggled into the envelope is rejected at parse time.

**PyYAML became a direct dependency rather than an optional one.** Corpus specifications are
hand-authored and are therefore YAML, so the parser is needed on the default path. It is the only
YAML consumer in the project. Timelines stay JSON: they are machine-written.

**Schema generation is `python -m spectral_loom.schemas`**, writing deterministically (sorted
keys, two-space indent, trailing newline) and stamping the 2020-12 dialect and a versioned `$id`.
`tests/test_schemas.py` fails on drift, on a missing file, and on non-idempotent generation.
Pydantic's `JsonValue` renders as an empty `$def`, so the extension bags are `object` with
unconstrained values — accurate, since their vocabulary belongs to the generator, not to us.
