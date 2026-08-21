---
id: tsk_01M0H0CVK38SZGKQQVMQGCAPSM
sequence: 22
kind: task
status: closed
sprint: spr_01M0GY4NYH1Q6R9HS0X7QKXSH4
created: 2026-08-20
closed: 2026-08-20
---

# Make the floor movable hypothetically, and the review completable

## Objective

Let the absolute flux floor be moved *hypothetically*, so that finding 3 can be settled by ear
rather than by argument, and add the two ergonomics the review has been visibly missing.

## Acceptance criteria

- A floor control redraws which peaks the rule *would* accept at another floor, including peaks
  currently below it and therefore invisible. Nothing is written; the compiled floor stays marked.
- Hypothetical acceptances are visually distinct from both accepted onsets and declined peaks, and
  can be auditioned like anything else, so "is that the shuffle?" is answerable by listening.
- The page derives acceptance from curves the compiler produced, and re-implements only the
  comparison — never the novelty, the median, or the peak picking.
- It checks its own derivation against the compiler's own list at the compiled floor, and says so on
  screen when they disagree.
- All four outputs' onsets are visible on one shared axis, so a coincidence between tracks can be
  seen without leaving the track being reviewed — with the caveat on screen that coincidence alone
  establishes nothing.
- A reviewer can mark a claim while listening and copy the accumulated marks out as text, so a
  review is completable and its findings arrive with their numbers attached.
- Marks live in the browser only. The page still writes nothing, anywhere.
- The compiled timeline stays byte-identical.

## Result

Done. Three additions: the floor control Henry asked for, and two ergonomics the review had been
visibly missing.

### The floor control

A slider and a number, defaulting to the compiled 20. Moving it redraws what this same rule *would*
accept — dashed purple for what it would gain, a red cross through any claim it would lose, and a
running `+16 / -0` beside the control. Both directions, because a control that only showed gains
would be quietly arguing for lowering it.

**It derives, it does not re-implement.** The rule is `flux >= multiplier * local_median + floor`,
so the floor is a constant added to an adaptive half that does not depend on it. The sidecar now
ships every local maximum with its flux and that adaptive half, and the page does one comparison per
peak plus the minimum-gap walk. The novelty, the running median and the peak picking — the three
parts worth duplicating badly — stay in Python.

**And it audits itself against the compiler, on every track.** At the compiled floor the derivation
must reproduce the compiler's own accepted list exactly or the banner turns red and says to trust
the timeline instead. Driven in the browser it reproduced all four: 153, 95, 97, 0. The same
invariant is asserted from Python so CI holds it too — if it ever breaks, the page's own check would
be the only thing between a reviewer and a fabricated event.

At floor 5 on `drums` it produces exactly the +16 that finding 3 measured, so the shuffle can now be
auditioned instead of argued about.

### All outputs on one axis

Four rows, one per model output, every accepted onset on the shared time axis, the reviewed track
highlighted. Click a tick to jump to that output and select that onset.

This exists because "is kick leakage causing false bass onsets?" is a printed review question that
could not be answered in the page — finding the drums hit 35 ms before the disputed bass onset in
finding 2 meant leaving the instrument for a Python shell. It carries its own caveat in red, because
the lane is exactly the sort of thing that invites a wrong conclusion: **every** accepted bass onset
in the interval from finding 2 coincides with something on another output, and parts played together
coincide just as leakage does. The lane says where to look, never what is true.

`vocals` rendering as a visibly empty row is worth more than the sentence about it.

### Review marks

`M` marks whatever is selected — a claim, a declined peak, a what-if, or just the playhead — and the
mark carries the numbers with it. `copy marks as text` produces markdown with the timeline's sha256
and the compiled floor at the top.

The reason this earns its place is the shape of this review: findings have been arriving as
screenshots and prose, and every one of them has needed a round trip through a Python shell to
recover its numbers. A mark carries them from the start.

**It is not a verdict store.** Marks live in the browser tab and nowhere else, the page still
contains no writer of any kind — a test enumerates `XMLHttpRequest`, `sendBeacon`, `localStorage`,
`sessionStorage`, `indexedDB` and `POST` and asserts every one of them absent — and the panel says
plainly that closing the tab loses them and the clipboard is the way out. A page that persisted a
reviewer's judgements would be one refactor away from being consulted as though it held them.

### One bug worth recording

The first build was dead on arrival with `SyntaxError: Invalid or unexpected token`, and the cause
is a trap in this file's shape: the page template is a non-raw triple-quoted Python string, so a
`\n` written inside JavaScript is consumed by *Python's* parser and becomes a real newline in the
middle of a JS string literal. It has to be `\\n` in the module source. Every Python test passed
while the page did not execute at all, which is the second time in two sessions that only opening
the page in a browser found the failure.

### Cost

Eight new hermetic tests. The compiled timeline is byte-identical:
`sha256:47e0178cc5b940c4545104c6c4eedb73b5f04d044f4e00b22dce23a583c977c4`.
