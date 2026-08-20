---
id: spr_01M0GPVMBCYCX68KZF76QFQ5QS
sequence: 3
kind: sprint
status: closed
created: 2026-08-20
closed: 2026-08-20
---

# Inspect the first specimen through separation

## Goal

Take the one specimen a human has now accepted, run the pinned Demucs over exactly those bytes,
and build the smallest instrument that lets Henry interrogate the resulting stems honestly.

The round tells one story and stops in the middle of it:

```text
human accepts exact source bytes
    → pinned Demucs separates exact source bytes
    → outputs are attributable and reproducible
    → human can interrogate all stems synchronously
    → stop for human judgment
```

Gate 2 of `docs/roadmap.md` becomes durably passed rather than passed-in-a-conversation. Gate 3
gets its machinery and its evidence, and then waits, because gate 3 is not passed by producing
stems — it is passed by a human hearing them.

## Rationale

Sprint 2 ended with a candidate nobody had heard and a repository that correctly said so. Henry
has now heard it and accepted it. That acceptance currently exists nowhere a clean clone could
find, and the WAV it is about is untracked — so unless it is written down in a form that names
the exact bytes, the project's own record still says the candidate is unjudged, and every
downstream stage would be trusting a directory name.

The specimen directory name is the weakest possible link between a human's ears and a byte
stream. `sparse-funk-exposed-bass` is a *specimen id*: it names an intent, and it survives
regeneration. Regenerate with a changed prompt and the same id points at different audio that
nobody has listened to. Separation must therefore require the accepted **hash**, mechanically,
before it loads a weight.

The stems are the other half. Every later inference in this project — activity, onsets, notes —
reads stem files rather than the mix. An unheard stem is an unexamined assumption sitting under
gates 4 and 5, and "Demucs ran without raising" is not evidence that a bass line survived. But
auditioning four stems plus a mix by opening five unrelated files in a media player is bad
enough that it will not actually be done carefully, and a gate that is inconvenient to judge is
a gate that gets waved through. The instrument is not a nicety; it is what makes the honest
answer cheaper than the lazy one.

## Success criteria

- Gate 2's acceptance survives a clean clone: tracked, machine-readable, naming the exact
  accepted sha256, the reviewer, the date, and each criterion response — and phrased so that
  nothing the prompt *asked for* is restated as something the audio *contains*.
- A rejection is representable in the same form, because a record that can only say yes is a
  marketing document.
- Separation refuses to run on bytes no human accepted, and says which hash it wanted and which
  it found.
- Separation loads the pinned HTDemucs snapshot directly and never resolves a moving upstream
  revision; it downloads nothing.
- The backend actually used is chosen explicitly and recorded. There is no silent fall back from
  MPS to CPU; an unavailable backend is a refusal, and a CPU run is a deliberate flag that
  reaches the provenance, the cache key, and the printed report.
- Every output stem carries its own hash, duration, sample rate and channel count, and is
  labelled as *the separator's own output name* rather than as a verified instrument.
- A second identical invocation is a verified cache hit: same key, every declared output present,
  every hash still matching. A partial or corrupted prior run is not mistaken for one.
- Engineering diagnostics — stem sum, residual, and their measured error — are reported as
  diagnostics, with no invented pass threshold.
- One command produces and opens a local, loopback-only exhibit in which all lanes share a single
  transport clock, and in which provenance is inspectable without dominating the screen.
- The default environment stays light, the hermetic suite stays hermetic, and no audio, weights,
  or review assets are tracked.

## Non-goals

- Deciding whether the separation is any good. Henry is the gate 3 oracle, and this round is not
  entitled to an opinion about what the stems sound like.
- `song.timeline.json` production, activity detection, onset inference, Basic Pitch, note events,
  or any analytical or artistic projection. Those are gates 4 onward and they read stems that
  have not yet been judged.
- A second specimen, a changed prompt, or a corpus.
- A generalized UI, a plugin system, a job scheduler, or a cache framework. Two cached stages is
  not enough cases to generalize from.
- Automatic recovery from a cabinet asset that has become unavailable. Noticing and choosing are
  different problems, and only the first one is cheap.
- Pushing commits.

## Retrospective (2026-08-20)

Every success criterion met. Five tasks closed, one decision, no dragons opened or closed.
**Gate 2 passes and is now durable. Gate 3 has its machinery, its evidence, and no verdict.**

### What the round changed about what this project believed

**A specimen id was quietly load-bearing, and it should not have been.** Everything downstream was
about to gate on `corpus/generated/<specimen>/`, and a specimen id names an *intent* that
deliberately survives regeneration. One prompt edit and that path resolves to audio nobody has
heard, with nothing anywhere raising its voice. The fix is small — hash-keyed reviews and
`require_accepted(root, id, hash)` — but the class of bug is the one this whole ladder exists to
prevent, and it was invisible until a stage actually needed a precondition.

**The four truth layers do not classify everything, and that is not a gap in them.**
`requested`, `observed`, `inferred`, `corrected` classify *claims about a recording*. "These bytes
are a usable specimen" is a claim about the project. Filing it under `corrected` would have invented
a `tool_revision` for a person and widened that layer from "a human overrode this inference" to "a
human said something", which is precisely the drift `principle:1` is written to prevent.
[[dcn_01M0KDMDVCJPSBVBSD3AC8MSVN]] says so explicitly rather than leaving it to be re-litigated.

**Upstream's default was wrong for this project, for a reason nobody would guess from the docs.**
`apply_model`'s `shifts=1` averages predictions over a time offset drawn from the *unseeded global
RNG*. Sprint 2 established that generation is byte-reproducible on MPS; accepting the upstream
default would have thrown that away at the very next stage, and the manifest's recorded parameters
would not have reproduced its own outputs. `shifts=0`, recorded, with the reason.

**The Hugging Face hub refuses to distinguish "deleted" from "private".** A request for a repository
that does not exist answers `401 Invalid username or password` — byte-identical to the answer for
one you lack access to. This was measured, not read. It is the single most useful thing the sentinel
learned, because a monitor that reported the obvious reading would eventually wake somebody up to
mourn an artifact that was merely behind an auth wall.

**Convenience is an evidence-integrity feature, not a nicety.** The Stem Observatory is the largest
thing built this round and it produces no data at all. It exists because a gate whose evidence is
inconvenient to examine is a gate that gets waved through, and auditioning four stems by opening
four unrelated files in a media player is exactly that inconvenient. Making the careful answer
cheaper than the lazy one is load-bearing.

### What exists that did not

Two new contracts with generated schemas — `SpecimenReview` and `SeparationManifest`. Three new
modules: `review`, `separate`, `observatory`, plus `hashing`, which three of them wanted. Three new
CLI commands — `accept`, `separate`, `review-separation` — all routed. A sentinel script and a
weekly workflow separate from hermetic CI. **224 hermetic tests, up from 131**, one `needs_model`
test outside CI, and one tracked review file.

47 MB of stems and diagnostics on this machine, none of it tracked. One 25 KB generated page, also
untracked.

### Two habits worth keeping

**Corroborate a measurement with a different code path.** The stage computes its reconstruction
residual through julius, the resampler `demucs` ships. Recomputing it with `scipy.signal.resample_poly`
and NumPy — separate resampler, separate summation — gave −30.11 dB against the stage's −30.11 dB.
Agreement to four decimals means the number describes the separation rather than this project's
arithmetic. A single-implementation measurement is a hypothesis.

**Prove the guard fires.** A cache check that always says "hit" is indistinguishable from one that
works. Nine bytes appended to `vocals.wav` produced a refusal naming the file; restoring it restored
the hit. Same discipline as sprint 2's negative control on the bootstrap's network guard.

### What is unmeasured, stated so a later round does not mistake it for settled

- **The stems.** Nobody has heard them. `bass.wav` is what HTDemucs assigned to its `bass` output,
  and whether a bass line survived is exactly the open question. Every number in `task:13` is
  engineering measurement and none of it is entitled to an opinion.
- **`bass × other` envelope correlation is +0.165** where every other pair is within ±0.05 of zero.
  Consistent with two parts playing at the same times, and equally consistent with leakage between
  them. This round cannot tell the difference; it is a reason to listen, not a finding.
- **The residual has no reference point.** −30.11 dB is a number to compare the *next* run against.
  This project has no evidence for a pass threshold and asserts none.
- **CPU separation has never run.** `--device cpu` is implemented, refuses to be arrived at by
  accident, and has only ever been observed refusing to overwrite an MPS result.
- **CI has still never run**, and the availability workflow has never fired.
- **Linux is still unexercised.** Everything measured here is one Apple silicon host.

### Next

Henry listens. `./loom review-separation sparse-funk-exposed-bass`, `1`–`4`, `A`, `R`, `[` and `]`.
The questions are printed beside the URL. **Gate 3 is not passed by these files existing**, and
nothing downstream — no timeline, no activity, no onsets, no Basic Pitch, no projection, no second
specimen — starts before he answers.
