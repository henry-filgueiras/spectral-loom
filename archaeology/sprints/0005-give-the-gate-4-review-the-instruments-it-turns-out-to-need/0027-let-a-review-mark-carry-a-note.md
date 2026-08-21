---
id: tsk_01M0JW3QMW2JZ156Q5WA8Q0P86
sequence: 27
kind: task
status: closed
sprint: spr_01M0GY4NYH1Q6R9HS0X7QKXSH4
created: 2026-08-21
closed: 2026-08-21
---

# Let a review mark carry a note

## Objective

Let a mark carry a note, so that a batch of marks can describe several different things instead of
being useful only when every row means the same thing.

## Acceptance criteria

- Any mark can carry free text, typed without reaching for the mouse.
- `M` leaves the cursor in the new row's note, so a thought can be written while it is still the
  reason the mark exists.
- Typing does not fire the keyboard shortcuts, and the transport is untouched by a space.
- Editing a note does not re-render the list and steal the cursor mid-word.
- Notes travel in the copied markdown, and a pipe inside one cannot split its own row.
- The page still writes nothing anywhere.

## Result

Done, and the request diagnosed a real limit rather than asking for a convenience.

Henry: *"right now batching marks for you only works if i scan through the song for a single type of
classification mismatch"*. That is exactly right, and it was making the review linear when it did
not need to be — a pass through the track produces a false positive, two missed hammer-ons and a
cluster worth explaining, and without notes those three have to be three separate passes.

`M` now leaves the cursor in the new row's note. The intent is that a thought gets written while it
is still the reason the mark exists, rather than reconstructed later from a timestamp.

Four details that make it usable rather than merely present:

- **Typing does not fire the shortcuts.** `c`, `m` and space are all letters someone will type into
  a note, and the existing `e.target.tagName === 'INPUT'` guard already covered it — verified in a
  browser rather than assumed, including that a space does not toggle the transport.
- **A note is written straight onto the mark without re-rendering the list.** Re-rendering per
  keystroke would take the cursor away mid-word, which is the whole reason to type in the row rather
  than in a separate box.
- **`Enter` and `Escape` blur**, so the shortcuts come back without a mouse.
- **A pipe inside a note is escaped**, or it would split the very row it is describing.

Notes travel in the copied markdown as their own column. The page still contains no writer; marks
and their notes live in the tab and leave through the clipboard.
