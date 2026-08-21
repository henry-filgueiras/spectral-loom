---
id: tsk_01M0GV2MEED2QY1JR1CYPEGNCW
sequence: 18
kind: task
status: closed
sprint: spr_01M0GV19568TPVR34C47C2NPVD
created: 2026-08-20
closed: 2026-08-20
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

## Result

Done. `spectral-loom compile` exists, is routed through `./loom`, and produces a byte-identical
document for unchanged inputs.

### The refusals

Both human verdicts are mechanical preconditions, checked before a sample is read, and neither is
satisfiable by a path. Gate 2's review must match the source hash; gate 3's must match the
separation manifest's own content hash; every stem must be present and must hash to what *both*
records say — the manifest and the review are checked separately, because a file that matches one
and not the other is a different problem and which one it disagrees with is worth knowing. The
source recording must be present and unchanged, even though the analysis never reads it, because a
timeline is a set of claims about a recording and a claim nobody can check is not evidence. Stems
whose durations cannot share the source's timeline are a refusal; a nonzero temporal offset measured
by the separation is a *notice*, because this project has no threshold for it and inventing one
would assert a pass mark nobody earned.

All of it is tested against a synthesized repository, including the case that matters most: a
separation manifest edited after the review no longer resolves, and the refusal names both hashes.

### The document

Five provenance stages in production order — `generate` and `separate` copied verbatim from the
records that already carry them, then `activity.measure`, `activity.interval`,
`onset.spectral_flux`. Copying the first two rather than restating them keeps the prompt labelled
`requested` and the separator's opinion labelled `inferred`, and stops the stems appearing from
nowhere. The measurement is `observed`; the two rules over it are `inferred`.

`source_audio` stays the original 48 kHz recording while every event cites a 44.1 kHz stem as
evidence, which is the one piece of this that is easy to get wrong: a timeline about the resampled
intermediate would be a timeline nobody could check against the file they hold.

Tracks are `htdemucs.<output>`, named for the model output that produced them. A test asserts the
strings `guitar` and `synth` do not appear anywhere in the document.

No event carries a confidence. The schema has the field; nothing here produces a calibrated value
for it, and scaling a novelty statistic into [0, 1] would manufacture one out of arithmetic. An
onset carries its raw flux, the threshold it beat, the margin between them, the local median, and
the level of the frame it was found in — which is what a person needs in order to disagree.

### Determinism

Designed in rather than hoped for. The canonical serialization is one function, used everywhere.
The analysis stages carry no `started_at`, no `duration_ms`, and no `runtime`; those three fields
are exactly what would make the document different every time it was produced from identical
inputs, and they live in a `compile-receipt.json` beside it instead. Every float is rounded at a
stated precision, and negative zero is normalized away, because `-0.0` and `0.0` compare equal and
serialize differently. Events sort by `(start, type rank, end)` with the type ranks fixed in a
literal rather than derived from a set.

The tests look for the *classes* of nondeterminism by name — a local path, a temporary directory, a
clock in a stage that should not have one — rather than only comparing two runs, because two
compiles a millisecond apart can agree by luck.

The receipt is deliberately not a published contract. `schemas/` is the language-neutral surface
another implementation reads; a local build record that only this module writes has no business in
it.

### The cache

A hit requires the recomputed key to match, the stems to still hash as recorded, the declared
timeline to be present, and that document to still hash to what the receipt recorded. All four
were made to fail on purpose, and the reason is prose rather than a boolean, because
`docs/provenance.md` says a run that should have hit cache and did not is a bug report.

A previous compile is replaced without ceremony — it is regenerable in seconds from inputs that are
already verified — but a directory containing anything *else* stops the run rather than being
deleted. Proportionate rather than uniform, and the difference is stated in the code.

### Cost

Sixty new hermetic tests across `test_analysis.py` and `test_timeline.py`, all on synthesized WAVs
in `tmp_path`. The suite went from 249 to 309 and still opens no socket and loads no weight.
