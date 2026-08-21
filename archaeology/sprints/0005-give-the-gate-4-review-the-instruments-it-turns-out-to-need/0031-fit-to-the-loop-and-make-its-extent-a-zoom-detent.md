---
id: tsk_01M0K0KXVBV2Y038MEWHK7J0SB
sequence: 31
kind: task
status: closed
sprint: spr_01M0GY4NYH1Q6R9HS0X7QKXSH4
created: 2026-08-21
closed: 2026-08-21
---

# Fit to the loop, and make its extent a zoom detent

## Objective

Make the loop the thing the view organises itself around, and stop the loop's highlight painting
outside the lanes.

## Acceptance criteria

- `fit` fits the loop with a margin; the whole file is still reachable, as its own action.
- The loop's extent is a detent when zooming, in both directions, and one more press goes past it.
- The detent tolerates landing near it, rather than leaving a press that travels a few percent.
- The loop highlight cannot paint over the label column when the view is zoomed inside the loop.

## Result

Three quality-of-life fixes, all from watching a real review run into them.

### `fit` fits the loop

It zoomed out to the whole forty-five seconds, which is almost never what "fit" was wanted for once
a region has been chosen. It now fits the loop plus a margin of twenty percent of its own length —
and falls back to the whole file when there is no loop, which is the only sensible reading. The
whole file is still one press away as `shift-F`, and its own button.

Deliberately distinct from the wider window an audition opens: an audition shows more context than
`fit` does, so pressing `fit` after auditioning a claim tightens onto it. That is useful rather than
inconsistent.

### The loop's extent is a detent

Zooming in from the whole file now stops at the loop's extent on the way past — Henry's "last chance
before becoming a microscope" — and coming back out from a close view settles there first. One more
press goes past it in either direction.

The first version had a strict crossing test and produced a wasted press: 22.5 s, 11.25 s, **5.63 s**,
5.60 s. Landing within twenty percent of the detent now counts as arriving, so the sequence is
22.5, 11.25, **5.6**, 2.8, 1.4. It cannot stick, because once the view *is* the detent the next press
is neither crossing nor near it.

### The highlight stayed in its lane

Zoomed inside a loop, the loop's box is positioned at a negative offset — measured at -5946 px in
one case — and painted across the label column. `overflow: hidden` on the overlay, which also fixes
the right edge Henry correctly guessed was broken too.

Worth recording how this was checked: `getBoundingClientRect()` still reports the element at -5946,
because `overflow: hidden` clips *painting* and not layout. The rect test therefore says the bug is
unfixed when it is fixed, and the only honest check was a screenshot. A test that measured the rect
would have failed forever against correct behaviour.
