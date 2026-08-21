---
id: ide_01M0K5XDNSPK6KVYTRXYGZ119R
sequence: 1
kind: idea
status: parked
created: 2026-08-21
---

# Distinguish percussion categories by band share, without claiming an instrument

## Problem

Gate 4's reviewer, asked whether the three event types are useful for synchronized visual work,
answered yes and immediately named what is missing: *"in an ideal world i would want to further
disambiguate between drum sound categories (any cymbal, any toms, hi-hat, bass drum)."*

The timeline currently says an onset happened in the `drums` output. It cannot say a kick happened,
and nothing downstream can either. For visual work that matters more than it sounds: a kick, a
hi-hat and a crash are three different visual events, and 153 undifferentiated onsets on one track
is a rhythm without a texture.

The evidence that this is reachable rather than speculative is already in the review. Sub-floor
drums peaks put **64.2% of their rise above 4 kHz** against 35.1% for accepted onsets; the ghost
note at 19.841 is at **88.5%**; the confirmed leakage at 12.190 separated a broadband drum transient
(53.5% below 300 Hz) from a bass-shaped one (97.6%) on exactly this basis. A band-share vector
already discriminates these categories in every case the review happened to look at.

## Sketch

An additional event namespace on the existing vocabulary — the point of an open vocabulary is that
this is not a schema change. Something like `onset.percussive` carrying a band-share payload, or a
separate `timbre.*` observation attached to an existing onset.

The cheap version is a deterministic band-share classifier: a handful of fixed bands, a rule stated
in full, and a `confidence` left absent because a band ratio is not a probability. The expensive
version is a trained classifier, which is a model, which is a cabinet entry, a pinned revision, and
a gate of its own.

The cheap version is the one this project should try first, for the same reason the onset detector
is spectral flux rather than a neural net: a rule a person can be shown and can argue with beats an
opinion they cannot inspect, and gate 4 has just demonstrated how much argument a reviewer will
actually produce.

## Boundaries

**This is instrument classification, and this project has said no to it once already.** Sprint 4's
non-goals exclude "instrument classification" and "splitting `other` into guessed instruments", and
`dragon:1` warns about encoding a musical ontology the evidence will not fit. A kick/snare/hat
taxonomy *is* an ontology, and the reason it might be admissible where "guitar" is not is that the
categories are defined by their acoustics rather than by their instrument identity — a band-share
rule says "broadband transient", not "this is a kick".

That distinction is load-bearing and easy to lose. `model_output: drums` survived this project's
review precisely because it never claimed to be a verified instrument. A percussion category would
have to be equally careful, and the naming is where it would go wrong first.

**It should not be attempted on `other`.** Finding 14 established that on a stem holding several
voices, the measurements available cannot attribute a partial to a voice. A timbre classifier there
would be confidently wrong.

**And it is behind the unresolved question.** `dragon:4` says `activity.interval` does not yet mean
one thing. Adding a second vocabulary while the first is unsettled is how a schema acquires two
half-designed ideas instead of one finished one.

## Evidence

Adopt when there is a second specimen with materially different percussion, so that a band-share
rule can be shown not to be fitted to one drum kit — and after `dragon:4` is either resolved or
explicitly deferred with a reason.

Reject if a band-share rule turns out to need per-specimen tuning, which would make it a fit rather
than a rule, or if the naming cannot be made to distinguish "broadband transient" from "kick drum"
in a way that survives a reviewer reading it quickly.
