---
id: spr_01M0GPVMBCYCX68KZF76QFQ5QS
sequence: 3
kind: sprint
status: active
created: 2026-08-20
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
