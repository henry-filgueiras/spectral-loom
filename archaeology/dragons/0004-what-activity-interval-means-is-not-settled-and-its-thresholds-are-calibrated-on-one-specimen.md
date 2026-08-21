---
id: drg_01M0GWB6CM4PG9ZB48P4NB34V6
sequence: 4
kind: dragon
status: open
created: 2026-08-20
---

# What activity.interval means is not settled, and its thresholds are calibrated on one specimen

## Context

`docs/roadmap.md` treats `activity.interval` as a settled, obvious thing — "compile a timeline from
stem activity and onsets" — and running it on real audio for the first time made it less obvious,
not more.

**One rule produced at least three different musical meanings.** The rule is one rule: cross
-50 dBFS, stay active until you fall below -56, merge gaps under 100 ms, discard what is shorter
than 100 ms. Applied to the accepted separation it produced:

- `bass` — 29 intervals covering 79.6% of the timeline. These plausibly correspond to *phrases*:
  the arrangement leaves space between them and the intervals fall in that space.
- `drums` — 50 intervals covering 74.0%. These cannot be phrases; the drums are continuous in this
  arrangement. They look like the *decay envelopes of individual hits*, and the gaps between them
  are the gaps between one hit's decay and the next hit's attack.
- `other` — **one** interval covering 92.8%. Technically correct, semantically nearly empty: the
  answer is "this track is on".
- `vocals` — zero, correctly.

So one event type is carrying phrase structure, note-decay structure, and "the track exists",
depending only on what happens to be in the track — and the timeline does not distinguish them. A
projection that drew all four the same way would be drawing three different things in one visual
language. That is not a bug in the rule; the rule does what it says. It is that the *name*
`activity` promises more structure than the measurement delivers, and a later stage that consumed
intervals as though they were phrases would be reading something that is not there.

**And the thresholds are calibrated against one specimen's absolute level.** `decision:11` chose
absolute dBFS thresholds and gave the evidence: they sit on a plateau across a ten-decibel sweep,
and they keep the near-silent `vocals` output unclaimed. That argument is sound *for this
recording*. It says nothing about a mix mastered thirty decibels quieter, which would produce a
timeline with no activity in it and would fail **silently** — well-formed, valid, claiming nothing,
with nothing in it saying why.

The two problems meet: the thing that would tell you the thresholds were wrong for a new specimen is
knowing what `activity` is supposed to *mean* for that specimen, which is exactly what is unsettled.

## Question

Does `activity.interval` name one thing, or is it three things wearing one label — and if it is
three, is the fix a vocabulary this project has not earned yet, or an admission in the projections
that the same event type means different things on different tracks?

Underneath it: is an absolute level threshold a property of music, or of this recording?

## Constraints

- **Per-track normalization is closed.** `decision:11` rejects it, with the evidence, and nothing
  here reopens that: it would make `other` produce structure by making its quiet moments relatively
  loud, and it would have invented events in `vocals`.
- **Tuning until `other` splits** is fitting one specimen and calling it a general truth.
- **Adding a `phrase` event type now** is inventing an ontology ahead of the evidence, which is
  `dragon:1` exactly.
- Generating a second specimen is forbidden until a human has spot-checked this timeline, by
  gate 4's own terms.

## Candidate direction

Wait, and let the projections carry the ambiguity honestly in the meantime.

The compiler already records the whole rule in the provenance and in the cache key, and the Timeline
Observatory draws the measured curve with both thresholds on it, so a person looking at an interval
can see exactly which rule produced it. That does not settle what an interval *means*; it makes the
disagreement possible, which is the most this round is entitled to.

If a distinction turns out to be needed, the shape that fits this project is a new namespace rather
than a new field — the event vocabulary is open on purpose — and it should be introduced only once
there is evidence naming what the second thing is.

## Resolution criteria

Any of these, in rough order of cost:

- **Henry's gate 4 spot-check.** If the `bass` intervals begin and end where he hears phrases begin
  and end, and the `drums` intervals do not, that is direct evidence that one event type is carrying
  two meanings — obtainable with ears, this week, on a timeline that already exists.
- **A second specimen at a materially different absolute level**, which would say whether -50 dBFS
  is a property of music or of this recording.
- **A specimen with a genuinely sparse continuous part**, as opposed to `other`, which is on
  throughout — which would say whether the one-long-interval outcome is a property of the
  arrangement or of the rule.
- **A measurement of what fraction of a track's intervals a listener would call a phrase boundary.**
  The honest version of the question, and the expensive one.
