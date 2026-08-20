---
id: tsk_01M0GPWWCFFBTQSC3PKFSF3KXA
sequence: 14
kind: task
status: closed
sprint: spr_01M0GPVMBCYCX68KZF76QFQ5QS
created: 2026-08-20
closed: 2026-08-20
---

# Build the Stem Observatory

## Objective

Build the smallest local instrument that makes auditioning the separation honest and pleasant: one
transport clock, every lane, and provenance in reach.

It is a separation evidence microscope. It is not the analytical projection of gate 6 and it is
not a generalized UI.

## Acceptance criteria

- One command generates and opens it. Zero build step, zero framework, zero network beyond
  loopback, bound to loopback only.
- One shared clock across the source mix, every stem, and any diagnostic lane. No drift, which
  means no independently running audio elements.
- Play, pause, seek, a visible playhead, per-lane mute and solo, one-key switching between the
  source and the reconstructed stem sum, and loop regions for chewing on a phrase.
- Lanes are labelled with the model that made them — `HTDemucs · bass` — never as verified
  instruments. A reconstructed mix or residual is labelled an engineering diagnostic.
- Provenance is inspectable without dominating the screen: source and stem hashes, Demucs code
  identity, exact asset revision and signature, backend, parameters, elapsed time.
- Fails clearly when a required artifact is missing or its hash no longer matches.
- Audio is served from where it already is, not copied or embedded.
- Review assets stay untracked. Pure transformations are tested hermetically.

## Result

Done. `spectral-loom review-separation SPECIMEN` builds the page, serves it on loopback, opens it,
prints the checklist, and stops.

One HTML file, no build step, no framework, no npm, no CDN, ~25 KB. Python's `http.server` and Web
Audio, and nothing else.

### One clock, which is the whole technical point

Every lane is an `AudioBufferSourceNode` started at the same instant on one `AudioContext` timeline.
Independently running `<audio>` elements drift, and two lanes that drift are two lanes you cannot
compare — which would make solo, mute and A/B comparison actively misleading rather than merely
imprecise. Looping is `source.loop` with a shared `loopStart`/`loopEnd`, so it is sample-accurate
per source and identical across them rather than a `requestAnimationFrame` seek.

Verified in Chrome against the real specimen: seven lanes fetched and decoded, all reporting
45.0000 s, all seven `loop` flags set on a shared region, position still inside the region after
1.5 s of playback, no console errors.

Controls: `space` play/pause, `0` source, `1`–`4` solo one output, `A` all four outputs, `M` the
rendered sum, `R` the residual, `[` `]` loop bounds, `←` `→` seek 5 s, `esc` clear solo and loop,
click anywhere to seek, per-lane mute and solo buttons, waveform envelopes drawn from the decoded
buffers with one playhead spanning every lane.

### Honesty is what the tests defend

Lanes read `HTDemucs · bass`, with a caption saying it is the signal the model assigned to that
output and that it is not a verified instrument — asserted for every stem lane. The reconstruction
and residual are a third `kind`, coloured and captioned as **engineering diagnostics, not stems**,
because they are arithmetic rather than anybody's opinion. A diagnostic with no audio (`stem-levels`)
gets no lane, only a number.

A test renders the page and asserts it reaches no verdict: `acceptable`, `good enough`, `PASS`,
`FAIL`, `healthy` and `clean separation` all absent, and the sentence *"has no evidence for a pass
threshold and asserts none"* present.

Provenance is behind a disclosure — in reach while auditioning, not what you are looking at:
source and every stem hash, the review hash, `demucs==4.1.0` with its published digest, the loading
and applying symbols separately, `adefossez/HTDemucs@bf35a81b…`, the model signature, the backend,
the runtime, the start time, the elapsed time, every parameter, the cache key, and the truth layer
spelled out as *"inferred — a model's opinion at an exact revision"*.

### It fails rather than misleads

A missing stem, a stem whose hash no longer matches, a missing source, or a source that is not the
one that was separated are all refusals with the hashes printed. *"The residual sounds like silence"*
and *"the residual file is gone"* must not look the same to somebody judging a gate.

### Exposure

Loopback bind, ephemeral port by default. The server has **no document root**: it serves the index
and a fixed URL-to-file table the exhibit built, so there is nothing to traverse —
`GET /../../model-cabinet.toml` returns 404, checked. Audio is served from where it already lives;
nothing is copied and nothing is inlined, and a test asserts the page contains no `data:audio` and
no base64. The page contains no `http://`, `https://`, `<link`, or `src=`.

The generated page lands in the ignored `corpus/derived/<specimen>/review/`.

### It records no verdict

There is no `--accept` flag and there will not be one. Gate 3's verdict is not something a program
can produce, and a command that offered to write one would invite exactly the conflation this
project exists to avoid. It prints the questions, per output the separator actually emitted, and
gets out of the way.

23 hermetic tests over the manifest-to-exhibit transformation, the rendering, the refusals and the
whitelist. Playback sync is not browser-tested in CI; it was verified once, by hand, in a browser.
