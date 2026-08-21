---
id: tsk_01M0GV2MF10J4KTCFQZP0CXG3V
sequence: 20
kind: task
status: closed
sprint: spr_01M0GV19568TPVR34C47C2NPVD
created: 2026-08-20
closed: 2026-08-20
---

# Build the Timeline Observatory

## Objective

Build the smallest local surface that lets Henry falsify a timeline claim with his ears: click an
onset, hear the moment, and A/B the stem against the source mix.

## Acceptance criteria

- Loopback only, no external script, stylesheet, font or service, one shared Web Audio clock, audio
  served from the artifacts that already exist, generated assets ignored.
- Aligned lanes for the source, the selected stem, the activity measurement, the inferred intervals,
  and the onset hypotheses.
- The activity lane makes the rule visible: the measured curve, the enter and exit thresholds, and
  the intervals the rule produced.
- Clicking an onset seeks to it, loops a short window around it, and lets the stem and the source
  mix be swapped with one key.
- Clicking an interval loops it with a small context margin; an activity sample reveals its measured
  value and the thresholds it was compared against.
- Selecting an event shows its exact semantic record — type, times, confidence only where one truly
  exists, raw score, evidence artifact and hash, producing stage, and the parameters relevant to
  that claim — without requiring anyone to read JSON.
- Absence renders as absence of inference: zero intervals is reported as zero inferred under a
  stated rule.
- Any exploratory overlay is labelled hypothetical and cannot write to the timeline, its cache, or
  its review state.
- The same short region can be looped while switching among source and every model output, with the
  timeline claims staying aligned.
- The command is reachable through `./loom`.

## Result

Done. `spectral-loom review-timeline` builds a loopback page in which a timeline claim can be
clicked, heard, and A/B'd against the source mix.

### What it shows

Five aligned lanes on one Web Audio clock: the source waveform, the selected model output's
waveform, the measured activity curve with the enter and exit thresholds drawn *at their actual
levels*, the inferred intervals as filled spans, and the onset hypotheses as markers.

The activity lane is the part that took the most care. An interval's existence has to be readable
off the picture rather than reverse-engineered from a number, so the curve and both threshold lines
are drawn on the same dB axis, labelled, on opposite sides of their lines because six decibels is
about ten pixels and two labels above would have collided.

The thresholds are **read off the timeline's own provenance**, not restated in the page. A timeline
without an `activity.interval` stage is a refusal rather than a page with guessed lines on it.

### The interaction that matters

Clicking an onset — or `N`/`P` to step — selects it, loops a configurable window around it
(250 ms before, 400 ms after by default), *and zooms the view to that window* so what is seen
matches what is heard. `S` then swaps between the model output and the source mix while it repeats.
Clicking an interval does the same with a context margin. That is the whole point: evaluating
"is that actually an audible onset" costs a click and a keypress.

Comparative perception falls out of the same design rather than needing its own mode. `1`-`4`
switches the selected output — lanes and audio together — and `0` goes to the source mix, so a loop
set once can be heard through every output in turn with the claims staying aligned.

### Three refusals to make a lie impossible

**No marker encodes a probability.** All onset markers are the same height, because this detector
reports no calibrated confidence and a height that varied with flux would be read as one. The raw
statistic appears as a separate dot on a labelled scale, and as a number in the inspector, beside
the threshold it beat.

**Absence renders as absence of inference.** `htdemucs.vocals` reads "0 activity intervals inferred
under this rule and these thresholds. That is a statement about the detector, not about the
recording." A test asserts that sentence.

**The inspector quotes the document.** The page fetches `song.timeline.json` itself rather than a
summary built for it, so the record shown is the record on disk. Confidence renders as "absent —
this producer reports no calibrated confidence" rather than as a blank.

### The threshold explorer, and why it audits itself

Moving the enter/exit inputs redraws candidate intervals dashed, under a banner that says they are
hypothetical and that nothing has been written. It writes nothing: the page contains no `POST`, no
`XMLHttpRequest`, no `sendBeacon` and no `localStorage`, and tests assert each of those absences.

It does, unavoidably, re-implement in JavaScript a rule that lives in Python — which is a
duplication that could drift. So it checks itself: whenever the inputs are back at the compiled
thresholds it recomputes the intervals and compares the count with the timeline's, and if they
disagree the banner turns into "THIS PAGE DISAGREES WITH THE COMPILER … Trust the timeline, not this
overlay." Driven in a browser against the real specimen it reproduced all four tracks exactly —
50, 29, 1 and 0 intervals — with boundaries agreeing to within a microsecond.

### What was shared, and what was not

`serve()` and the file whitelist moved out of the Stem Observatory and are used by both. That is a
socket and a table of files; the two pages share nothing else, and neither is a step toward the
gate 6 projection.

### Verified in a browser, not only in tests

Driven through Chrome against the real specimen: all five lanes render, all four outputs decode,
stepping to an onset zooms and loops correctly, the inspector shows twenty-nine rows including the
absent confidence, the vocals lane shows the empty-state sentence, `Escape` clears loop, selection
and zoom, and the console is empty. One real bug was found that way and only that way — every
canvas needed an explicit CSS height, because a canvas with `width: 100%` and no CSS height scales
to preserve its attribute aspect ratio, which on a wide window made a 76-pixel lane six hundred
pixels tall and pushed the lanes below it off the screen. Lanes you cannot see at once are lanes
you cannot compare, which would have quietly defeated the point of the page.

Eighteen hermetic tests, none of which open a socket or decode audio.
