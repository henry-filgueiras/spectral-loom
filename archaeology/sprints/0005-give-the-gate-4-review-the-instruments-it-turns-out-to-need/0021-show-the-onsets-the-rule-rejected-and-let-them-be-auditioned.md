---
id: tsk_01M0GY4NYW20XW9FA0GSPB013P
sequence: 21
kind: task
status: closed
sprint: spr_01M0GY4NYH1Q6R9HS0X7QKXSH4
created: 2026-08-20
closed: 2026-08-20
---

# Show the onsets the rule rejected, and let them be auditioned

## Objective

Make a rejected onset candidate visible, clickable, and auditionable, so that the detector can be
judged on what it declined as well as on what it claimed.

## Acceptance criteria

- The onset lane shows the novelty curve and the adaptive threshold curve it was compared against,
  so that a threshold rising after a loud attack and swallowing the quiet articulation behind it is
  something a person can *see* rather than deduce.
- Local maxima that cleared the absolute floor and were then rejected by the full rule are drawn as
  candidates, in a style that cannot be mistaken for an accepted onset.
- A candidate is clickable and auditions exactly like an onset does: seek, short loop, and one key
  to swap the model output for the source mix.
- Selecting one shows why it was rejected — its novelty, the threshold, the margin, the local
  median, its own level, and which half of the rule turned it down — and says plainly that it is
  **not an event and is not in the timeline**.
- Candidates below the absolute floor are reported as a count rather than as markers, because
  showing them would bury the interesting ones in noise.
- Everything recomputed for review is produced by the same analysis code that produced the timeline,
  never by a second implementation of the rule in the page.
- The recomputed data is a review asset: ignored, regenerated on every run, and carrying inside
  itself a statement that it is not a semantic artifact.
- The compiled timeline is byte-identical before and after this change. A test asserts it.

## Result

Done. The onset lane now shows what the rule turned down as well as what it claimed, and a declined
peak can be clicked and auditioned exactly like an accepted one.

### What it draws

The lane became two rows. On top, markers: accepted onsets solid, declined peaks dashed, both the
same height, because the height must never encode magnitude. Underneath, the two curves the decision
was actually made on — the novelty this detector measured and the adaptive threshold it was compared
against — so a threshold rising after a loud attack and riding over the quiet articulation behind it
is now something a person can *see*.

Two rendering choices took a second attempt each, and both were caught by looking at the page rather
than by a test.

**The curve is scaled to the largest value in view, not in the track.** Pinned to the track maximum,
every quiet articulation drew flat against the axis when zoomed in — which is exactly the material
the lane exists to show. The axis maximum is relabelled as it changes, so the number is never
implied.

**The axis is logarithmic.** Spectral flux spans two orders of magnitude inside one track: a plucked
attack of 261 beside a hammer-on of 28. On a linear axis the second is invisible even after the
first fix. `log1p` is monotonic and fixes zero at zero, so **every crossing between the two curves
is exactly where it is in the numbers**, which is the only relationship this plot has to get right,
and the label says so.

### What it refuses to blur

Selecting a declined peak opens with `This is not a claim.` and `A DECLINED PEAK — not an event, and
not in the timeline`, then gives the numbers the decision was made on and which half of the rule
turned it down, in prose rather than as an enum. An accepted onset wins a tie when both are near the
click, because the claim is what the page is about and the declined peak is context for it.

Peaks below the absolute floor are **counted, not drawn**: 259 on `bass`, 488 on `vocals`. Drawing
them would bury the sixty-six that are worth looking at. The count is on screen so their absence is
stated rather than implied.

### Where the numbers come from

`spectral_loom.analysis.infer_onsets` — the same function, at the same parameters, that produced the
accepted onsets — now walks *every* local maximum on one code path and reports the ones it declined,
so a candidate's numbers are literally the numbers the decision was made on. The page draws arrays
and re-implements nothing. That is deliberate: the threshold explorer already duplicates the
interval rule in JavaScript and needs a self-check because of it, and this does not repeat that
mistake.

The recomputed data is a review asset — `corpus/derived/<specimen>/review/review-novelty.json`,
ignored, regenerated on every run — and it carries the disclaimer inside itself, because a JSON file
found on disk months later will be read without any of this context.

### The timeline did not move

`sha256:47e0178cc5b940c4545104c6c4eedb73b5f04d044f4e00b22dce23a583c977c4`, before and after. A
`RejectedCandidate` is a separate type from an `Onset` precisely so that it cannot reach a timeline
by accident, and the compiler reads only `.onsets`.

### What the tallies immediately showed

```
                accepted   declined above floor   below floor
  bass                95                     66           259
  drums              153                     17           163
  other               97                    271           170
  vocals               0                      0           488
```

Two things fall out that were not visible before and are not yet interpreted.

**`other` declined 271 peaks against 97 accepted** — nearly three rejections per claim, far out of
line with `drums` at 17. Consistent with an output holding several unresolved voices whose combined
activity keeps the local median high, and equally consistent with the rule being wrong for that
material. This round cannot tell the difference.

**Not one peak anywhere was declined by the minimum-gap rule.** Every rejection on every track is
`below_adaptive_threshold`. The gap rule is very nearly subsumed by the peak-radius rule that runs
before it — a radius of 3 frames already forces accepted peaks 46.4 ms apart, and the gap is 50 ms —
so it currently excludes almost nothing. Recorded, not acted on.

### Cost

Eleven new hermetic tests. The `min_gap` branch is reachable only by passing the parameter
explicitly, which is what the test that covers it does.
