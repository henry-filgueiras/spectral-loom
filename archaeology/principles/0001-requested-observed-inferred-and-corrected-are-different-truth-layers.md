---
id: prn_01M0GH5QAPD237HP9NV9B8AXM8
sequence: 1
kind: principle
status: active
created: 2026-08-20
---

# Requested, observed, inferred, and corrected are different truth layers

## Statement

A prompt is a request. A generator's parameters are a request. Neither is an observation about
the audio that came back, and neither may be presented as one.

Four truth layers exist and never collapse into one:

1. **requested** — what was asked for: prompt, seed, requested BPM, requested key, requested
   instruments. Authored before the audio existed.
2. **observed** — what the audio contains, measurable by anyone with the file.
3. **inferred** — what a named model at an exact revision concluded from the audio, with a
   confidence and a source interval.
4. **corrected** — what a human overrode, with the fact of the override recorded.

## Rationale

The whole project rests on the audio being the evidence. A generator asked for 96 BPM in D minor
with a clean guitar; the audio may be 92 BPM, may have drifted key, and may have no guitar in it
at all. If the timeline records the requested BPM as `bpm`, every downstream projection inherits
a fiction and no amount of later care recovers the distinction — the field has already lost the
information about where its value came from.

This is also the failure mode that makes generative-music tooling untrustworthy in general: the
prompt is the most convenient metadata available, and it is the least reliable.

## Application ordering

Applies before schema convenience and before rendering convenience. When a field would be easier
to consume flattened, it stays labelled anyway.

Concretely, in this repository:

- specification fields carrying requests are named `requested_*`, and the specification is not a
  timeline input for anything but provenance;
- timeline events carry `evidence` naming the artifact and interval they came from;
- every stage records `truth_layer` in its provenance;
- a human correction is a distinct provenance stage, not an edit that erases the inference.

## Counterpressure

Labelling is verbose. `requested_bpm` is uglier than `bpm`, and a renderer that just wants a
tempo will have to say which tempo it means. Accept the verbosity: the ugliness is the point,
because it is visible at the call site.

There is also pressure from the other direction — an inference is often the only value available,
and treating it as fact is the path of least resistance. A confidence of 0.97 is still an
inference.

## Failure signals

- A timeline field whose name does not say which layer it belongs to.
- A projection reading a specification instead of a timeline.
- An inferred value that survives into a report with no model revision attached.
- A human correction applied by editing an inferred artifact in place.
- Absence being reported as proof: "no guitar events" rendered as "there is no guitar". A
  negative inference is a failure to detect, not evidence of absence.
