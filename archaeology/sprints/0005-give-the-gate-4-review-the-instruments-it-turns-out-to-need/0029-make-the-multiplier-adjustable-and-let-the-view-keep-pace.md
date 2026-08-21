---
id: tsk_01M0JYM2HHGRBMTAZN5XVHAN65
sequence: 29
kind: task
status: closed
sprint: spr_01M0GY4NYH1Q6R9HS0X7QKXSH4
created: 2026-08-21
closed: 2026-08-21
---

# Make the multiplier adjustable, and let the view keep pace

## Objective

Make the other half of the onset rule adjustable, stop `M` typing itself into the note it just
opened, and let a zoomed view keep pace with playback.

## Acceptance criteria

- The multiplier is adjustable hypothetically, derived from what the compiler already computed
  rather than by re-deriving the novelty, the running median or the peak picking.
- The self-check covers both parameters, and still reproduces the compiler exactly on every track
  when both are at their compiled values.
- `M` opens its note without typing an `m` into it.
- A zoomed view follows the playhead while playing, without redrawing five canvases every frame,
  and without an audition's loop causing it to page.

## Result

Three things, and the first changed what the review can see.

### The multiplier

Finding 11 established that a quarter of the missed drums material is unreachable by the floor: the
adaptive term alone already exceeds its flux. Henry had spent the review moving the only dial he
had.

The multiplier is now adjustable on the same terms as the floor, and derived the same way. The
sidecar ships `compiled multiplier x local median` per peak, so another multiplier is that term
scaled — the novelty, the running median and the peak picking stay in Python, and the page still
re-implements only a comparison. The self-check now covers both parameters and still reproduces the
compiler exactly on all four outputs.

### What became visible immediately

```
                       drums  bass  vocals   admits 19.841
  floor 20, mult 2.0     153    95       0   no        <- compiled
  floor 20, mult 0.4     166   137       0   yes
  floor 10, mult 1.0     164   153       0   yes
  floor  5, mult 1.5     180   162       0   yes
  floor  0, mult 1.9     224   202     144   yes       <- vocals breaks
```

**There is a two-dimensional region that admits the quiet material and still leaves `vocals`
unclaimed**, and no single-parameter sweep could see it. The floor has to stay above about 5 or
`vocals` fills with noise regardless of the multiplier — but with the floor merely held there, the
multiplier can fall a long way.

`decision:11`'s sweep moved one parameter at a time. Its conclusion about absolute-versus-relative
survives; its implicit assumption that the floor was the parameter worth arguing about does not.

### A correction I owe

I told Henry the multiplier binds and "the floor is irrelevant" for 19.841. Imprecise: at the
compiled floor of 20, the floor alone leaves only 5.94 of headroom under a flux of 25.94, so the
multiplier would have to fall to 0.44 to reach it there. Neither dial reaches it alone at a sane
value — it takes both. The grid above is the accurate version.

### Two small fixes

`M` was typing an `m` into the note it had just focused: the keydown focused the field and the
browser's default action then inserted the character. One `preventDefault`.

And a zoomed view now follows the playhead, paging once per view-width with the playhead landing
near the left edge so what is coming stays visible. Paging rather than scrolling because every
redraw recomputes waveform peaks for five canvases; a guard stops the clamp at the end of the file
re-triggering every frame; and a loop that fits inside the view never pages, which is what lets
auditioning a claim and following a passage coexist.

Verified by calling the follower directly, because `requestAnimationFrame` reported **zero frames
per second** in the automated tab — throttled, as background tabs are. View 5-8 s paged to
7.21-10.21 s with the playhead at 7.66 s, span held.
