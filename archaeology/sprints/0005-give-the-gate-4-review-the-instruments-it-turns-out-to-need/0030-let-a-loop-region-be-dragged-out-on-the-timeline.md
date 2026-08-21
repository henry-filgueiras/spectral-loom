---
id: tsk_01M0JZF5Y4T48H2EQHXPB6S0NW
sequence: 30
kind: task
status: closed
sprint: spr_01M0GY4NYH1Q6R9HS0X7QKXSH4
created: 2026-08-21
closed: 2026-08-21
---

# Let a loop region be dragged out on the timeline

## Objective

Let a loop region be dragged out on the timeline, because specifying it visually beats four
keystrokes — and on a track that is one long interval it is the only way to work at all.

## Acceptance criteria

- Press, drag, release sets the loop; the direction of the drag does not matter.
- A click still does what a click did: seek, or pick the onset or interval under the cursor.
- The two are separated by distance, not by timing, and a small twitch counts as a click.
- The click that follows a real drag does not also seek.
- The suppression cannot outlive its gesture: a release that produces no click must not swallow the
  next one.
- A selection in progress looks different from a committed loop, and says how long it is.
- Touch works the same as a cursor, for free.

## Result

Done. Press, drag, release. Either direction.

**Pointer events rather than mouse events**, with pointer capture. That covers touch identically and
for free — which is worth having if the phone tunnel from sprint 5's digression ever gets built —
and capture means a drag that wanders off the strip still ends where it was released rather than
silently never ending.

**A drag and a click arrive as the same event sequence**, so they are separated by *distance*:
under four pixels the gesture falls through to the existing click behaviour, over it the click that
follows the release is suppressed. Distance rather than timing, because a slow deliberate click is
still a click and a fast flick is still a drag.

A selection in progress is drawn dashed and purple, distinct from a committed loop, so that letting
go is visibly the thing that commits it; the readout says how long it currently is.

### One real bug, found by testing rather than by reading

The suppression flag was cleared only when a click consumed it. But a release outside the strip
produces no click at all, so the flag stayed set and **swallowed the next legitimate click** — which
showed up in the browser as a plain click failing to seek, several actions after the drag that
caused it. Now cleared at the start of every gesture, so a stale flag cannot survive into a new one.

Verified in a browser across the cases that matter: a forward drag, a backward drag, a drag with no
trailing click followed by a plain click that must still seek, a drag whose own trailing click must
not seek, and a two-pixel twitch that must count as a click.

### Why it was asked for

Henry, on `other`: *"more annoying than i expected without something like this"*. That track is a
single 41.8-second interval, so `I` steps between nothing, and every region has to be built by hand
from four separate actions. `dragon:4` says the interval vocabulary carries no information on that
track; this is the same fact arriving as an ergonomic cost.
