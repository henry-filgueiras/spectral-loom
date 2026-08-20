---
id: dec_01M0GH33MZJYZYAKWT9G5QT8T5
sequence: 1
kind: decision
status: accepted
created: 2026-08-20
---

# Adopt the Spectral Loom compiler thesis

## Context

Music is normally handled either as an opaque waveform or as an authored score. Neither shape
supports the thing this project wants: a synchronized visual projection that can justify every
mark it draws by pointing at the audio that caused it.

A waveform carries all the evidence and none of the structure. A score carries structure that
was never observed — it is what someone intended, not what the recording contains. Generative
music makes the gap sharper, because a generator's prompt and parameters describe a *request*,
and the audio that comes back may or may not honour it.

## Decision

Spectral Loom is a compiler for music.

> Compile music into a source-grounded semantic timeline, then weave that timeline into
> synchronized analytical and artistic visual projections.

The pipeline the project is built toward:

```text
music generator
    -> song audio
    -> source separation
    -> stem-specific analysis
    -> song.timeline.json
    -> deterministic visual projections
```

The likely initial model cabinet is ACE-Step 1.5 for generation, Demucs for separation, and
Basic Pitch for note inference. None of them is installed, downloaded, or adapted yet, and the
architecture is deliberately arranged so that any of the three can be replaced without changing
the boundary artifact.

The word "compiler" is load-bearing rather than decorative. A compiler has a source of truth
(the audio), a typed intermediate representation (`song.timeline.json`), and back ends that may
disagree in style but not in meaning (the projections).

## Consequences

- The audio file, not the prompt and not the timeline, is the evidence-bearing source.
- Analysis stages are compiler passes: expensive, cacheable, and keyed by their inputs.
- Projections are back ends. They read the timeline and may not write to it.
- The project earns nothing by generating a corpus before one specimen has survived a listen,
  so the roadmap is a ladder of evidence gates rather than a feature backlog.
