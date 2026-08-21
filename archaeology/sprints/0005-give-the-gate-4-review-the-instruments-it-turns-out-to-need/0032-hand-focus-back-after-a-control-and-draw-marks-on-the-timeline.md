---
id: tsk_01M0K3BWFN0CTNFH8MKXN35K9W
sequence: 32
kind: task
status: closed
sprint: spr_01M0GY4NYH1Q6R9HS0X7QKXSH4
created: 2026-08-21
closed: 2026-08-21
---

# Hand focus back after a control, and draw marks on the timeline

## Objective

Stop controls swallowing the keyboard shortcuts, and stop a reviewer rediscovering claims already
examined.

## Acceptance criteria

- After a checkbox, button or slider is used, the shortcuts work again without clicking elsewhere.
- A field you type into keeps focus, because there the space bar means a space.
- Every mark is drawn across all lanes, distinguishable between the reviewed track and the others.
- The lines are positioned rather than rebuilt on each frame.

## Result

Two small things, both from a reviewer being slowed down by the instrument rather than by the
evidence.

**Focus.** A checkbox that keeps focus after being clicked swallows the space bar, so play/pause
silently stops working until you click somewhere neutral. Focus is now handed back after any click
except on a field you type into, where a space is a space. Verified for a checkbox, a button and a
slider — all three leave `document.body` focused — while a note field keeps focus, and the space bar
starts playback immediately after a control is used.

The cost is that a slider can no longer be nudged with the arrow keys after clicking it, since it no
longer holds focus. The number field beside each slider covers precise entry, and the arrows are
bound to seeking, which is what someone reaching for them during a review almost certainly wants.

**Marks on the timeline.** Every mark is now a dashed line across all lanes — bright for the
reviewed track, dim for the others, so a mark made on `drums` stays visible while looking at `bass`.
That matters more than it sounds: finding 13's leakage was a claim on two tracks at one instant.

Positioned rather than rebuilt on each frame, since marks change rarely and the view changes often.
