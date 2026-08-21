---
id: tsk_01M0H5AQAP841ET0BX0FEKHZ8J
sequence: 23
kind: task
status: closed
sprint: spr_01M0GY4NYH1Q6R9HS0X7QKXSH4
created: 2026-08-20
closed: 2026-08-20
---

# Move the page templates into files, so the escaping trap cannot recur

## Objective

Move both observatory page templates out of Python string literals and into real files, so that the
escaping trap that has broken the Timeline Observatory twice cannot happen a third time.

## Acceptance criteria

- Each page is a `.html` file beside its module, read verbatim at render time.
- The extraction is lossless: the rendered pages are byte-identical to what the string literals
  produced.
- The files ship in a built wheel; a page template that does not survive packaging is worse than one
  that is awkward to escape.
- A missing template is a refusal naming the file and where it was expected.
- A test fails if either module ever embeds a page again, because a template that creeps back into a
  module source brings the trap back with it and would pass every other test.

## Result

Done. Both pages are files now: `src/spectral_loom/pages/stem_observatory.html` and
`timeline_observatory.html`, read verbatim by a shared `load_page`.

### Why this was a bug fix and not tidiness

A template embedded in a non-raw triple-quoted Python string is decoded by **Python's** parser
before a browser ever sees it. A `\n` written inside JavaScript therefore became a real newline in
the middle of a JS string literal, and the page stopped parsing. It needed `\\n` in the module
source to reach the browser as `\n`.

That failed twice in two sessions, and both times **every Python test passed while the page did not
execute at all** — the tests assert what the page *says*, which is exactly as true of a page that
never runs. Reading a file removes the decoding step, so the bug is not fixed but unreachable.

### The extraction was proved lossless rather than assumed

The templates were pulled out with `ast.literal_eval` on the same literals Python was already
decoding at import, so the files on disk are by construction the strings that were being served.
Confirmed against the artifacts: both pages re-render byte-identical.

```
timeline page  fa0a2e76f8c13966ec029d601d8dd3a322a66154fd5eae25ebd6e164a8485ebb  before and after
stem page      f1c4a577057ae32ed88145d9699238d9c1c467bb60653fb27eb4680bb3c15a39  before and after
```

Driven in a browser afterwards: page loads, four tracks index, novelty loads, the floor self-check
passes, the raster renders, a mark round-trips, console empty.

### Packaging was the part that could have gone silently wrong

A template that does not ship is worse than one that is awkward to escape, because it fails only on
someone else's machine. A wheel was built and inspected: both files are in it at
`spectral_loom/pages/`. Hatchling includes non-Python files inside a declared package, so no
manifest change was needed — but that was verified rather than assumed.

### The regression guard

`tests/test_pages.py` walks each module's AST and fails if any string constant contains
`<!doctype html`. A template that creeps back into a module source brings the trap back with it and
would pass every other test in the suite, so the guard is about the *arrangement* rather than about
any page's contents. One test also asserts the literal byte sequence the old arrangement destroyed:
`join('\n')` present as an escape, and absent as a real newline.
