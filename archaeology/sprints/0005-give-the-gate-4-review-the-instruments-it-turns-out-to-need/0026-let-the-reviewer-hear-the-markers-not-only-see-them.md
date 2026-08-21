---
id: tsk_01M0JV6FB7HQ6214ZKVVP76HDC
sequence: 26
kind: task
status: closed
sprint: spr_01M0GY4NYH1Q6R9HS0X7QKXSH4
created: 2026-08-21
closed: 2026-08-21
---

# Let the reviewer hear the markers, not only see them

## Objective

Let a reviewer *hear* the markers, because judging whether one sits on an attack by looking at it
asks for tens of milliseconds of visual resolution against a waveform.

## Acceptance criteria

- Accepted onsets, declined peaks and what-ifs each click at their own pitch, and what clicks is
  exactly what the marker lane draws.
- The clicks are additive over whichever output is selected, not a thing you switch to instead.
- They ride the same transport as the audio, so they cannot drift and need no separate handling for
  looping.
- Changing the floor, the track, or the declined-peaks toggle updates them without the slider
  restarting playback on every pixel of travel.
- Nothing is written; the timeline is byte-identical.

## Result

Done. `C` toggles a click track; three pitches, level slider beside it.

### Why this and not better graphics

Henry's report was *"I'm just not good enough at linking the visual to the sound cue."* That is not a
skill gap, it is the wrong sense being asked to do the work. Two candidate onsets 82 ms apart are
about six pixels at full-file zoom and perhaps forty when zoomed to a second — and even at forty,
deciding which of two marks coincides with an attack means comparing a vertical line against a
waveform by eye. Sonified, the same judgement is immediate and needs no zoom: the click lands on the
attack or beside it.

This is also simply how onset detection has always been evaluated. It should have been in the first
version of the page.

### How it is built, and why that way

The clicks are **rendered into an AudioBuffer and played as another lane through the same
`start(when, at)` call as the audio**. The alternative — scheduling oscillators against
`ctx.currentTime` — would have had to re-derive loop wrapping, and would drift against the buffers
it is supposed to be judged against. A buffer that starts in the same call cannot drift from them.

What clicks is exactly what the marker lane draws: accepted onsets at 2400 Hz, declined peaks at
950 Hz when they are shown, what-ifs at 1550 Hz when the floor is not the compiled one. Three
pitches so that which kind is sounding needs no glance at the screen. Ten milliseconds,
exponentially decayed, so each click's own onset is unambiguous.

The lane is **additive**, deliberately excluded from the solo logic that switches between outputs:
the whole point is hearing it *over* the selected output rather than instead of it.

Rebuilds are debounced by 180 ms, because swapping the buffer restarts playback and the floor slider
fires on every pixel of travel.

### Verified in a browser

161 clicks on `bass` at the compiled floor — 95 accepted, 66 declined — rising to 186 with 25
what-ifs at floor 8.5. Click energy measured directly out of the rendered buffer: present at
23.626 and 23.708, silent at 23.400. With clicks on, the stem's gain stays at 1 and the click lane
sits at 0.225, so nothing is being replaced. Six sources run during an audition, one per lane
including the clicks, and the loop holds. Console clean.
