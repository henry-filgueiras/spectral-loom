---
id: tsk_01M0JX8SP21EH4HZW0863DQZV8
sequence: 28
kind: task
status: closed
sprint: spr_01M0GY4NYH1Q6R9HS0X7QKXSH4
created: 2026-08-21
closed: 2026-08-21
---

# Fix the loop-bound ratchet, and give intervals audible edges

## Objective

Fix the loop-bound ratchet, and make an interval's boundaries audible so that a sound heard in an
audition's context margin can be placed.

## Acceptance criteria

- Setting an in point and then an out point can *widen* the loop, repeatedly, from any position.
- A pending in point is visible, so pressing the key does not look like nothing happened.
- An out point with no in point has a reading that is never a surprise.
- The selected interval's edges are audible, without burying an onset scan under a hundred
  boundaries; every edge is available on request.
- The edges are in the buffer before the audition that needs them starts.

## Result

Two fixes, one of them a real bug inherited from the Stem Observatory.

### The ratchet

`[` and `]` could only ever *shrink* the loop, however many times they were pressed. The cause is
structural rather than a slip: while a loop is active, playback is confined to it, so the playhead
can never be outside it — and both keys set their bound from the playhead. Every press therefore
moved a bound inward. Henry's word for the result was "comical", which is fair.

`[` now begins a **new** selection: it sets the in point and clears the out point. That releases the
confinement, so the playhead can travel to wherever the new out point belongs. `]` then closes it,
swapping if the two arrived in the wrong order, and an out point with no in point reads as "from the
beginning to here" — the only reading that is never a surprise.

A pending in point is drawn as a dashed line with a prompt beside the clock, because otherwise
pressing `[` looks like nothing happened.

Verified in a browser: an in at 10 s and an out at 14 s gives a 4-second loop; a second pair at 11 s
and 20 s gives **nine** seconds. It widens.

### Audible interval edges

Henry: *"i can't tell if a sound that is unmarked at the beginning of the loop is overflow from the
previous interval or actually unmarked."* Auditioning an interval plays a context margin either
side, and nothing in the audio says where the span begins.

The selected interval's edges now click — 620 Hz entering, 420 Hz leaving, both well clear of the
onset tones — so the audition is heard as boundary, content, boundary. Only the selected span, so
scanning for onsets is not buried under a hundred boundaries; a checkbox turns on every edge for
when the intervals themselves are the subject.

One detail that matters: that rebuild is **synchronous**, unlike the debounced one behind the floor
slider. `audition()` runs immediately after `select()` and has to start a buffer that already
contains the edges it was selected for.
