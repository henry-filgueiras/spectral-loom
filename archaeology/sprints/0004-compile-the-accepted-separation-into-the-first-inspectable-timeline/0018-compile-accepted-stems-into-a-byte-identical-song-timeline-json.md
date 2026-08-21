---
id: tsk_01M0GV2MEED2QY1JR1CYPEGNCW
sequence: 18
kind: task
status: pending
sprint: spr_01M0GV19568TPVR34C47C2NPVD
created: 2026-08-20
---

# Compile accepted stems into a byte-identical song.timeline.json

## Objective

Add the smallest real compiler stage: accepted separation in, `song.timeline.json` out, with full
provenance and byte-identical output for unchanged inputs.

## Acceptance criteria

- The compiler refuses unless the specimen review matches the source hash, the separation review
  matches the separation manifest hash and every stem hash, every input file is present and hashes
  as recorded, the manifest is valid, and the stem durations are compatible with the source.
- `source_audio` remains the original accepted 48 kHz recording; events cite the 44.1 kHz stems as
  evidence and all times are seconds on the shared song timeline.
- Tracks are named for the model output that produced them; nothing is renamed to a guessed
  instrument.
- Provenance carries the whole lineage — generation, separation, activity measurement, interval
  inference, onset inference — in production order, with truth layers that do not collapse.
- Every event cites a producing stage, an evidence artifact, its hash, and its own source interval.
- Canonical bytes contain no wall-clock, no elapsed time, no temporary or absolute path, no random
  id, and no ordering that depends on traversal. Run telemetry lives outside the semantic document.
- A second identical invocation validates its inputs, reports a verified cache hit, and leaves
  byte-identical output with the same sha256. A corrupted or missing input or declared output
  invalidates reuse loudly.
- Hermetic tests over synthesized fixtures assert the semantics — measured windows, threshold and
  gap rules, onset timing within the documented resolution, near-silence staying unclaimed, stable
  ordering, resolvable provenance, byte-identical recompilation.
- The command is reachable through `./loom` and the router's completeness test knows about it.
