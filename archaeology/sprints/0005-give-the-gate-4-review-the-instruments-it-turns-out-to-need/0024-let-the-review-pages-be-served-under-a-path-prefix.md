---
id: tsk_01M0H8ZPVEK6JMNQJQM3AMC707
sequence: 24
kind: task
status: closed
sprint: spr_01M0GY4NYH1Q6R9HS0X7QKXSH4
created: 2026-08-20
closed: 2026-08-20
---

# Let the review pages be served under a path prefix

## Objective

Make the review pages reference their own artifacts relatively, so that serving one behind a path
prefix is possible without the server ever learning that a prefix exists.

## Acceptance criteria

- Nothing the page fetches is written as an absolute path, so every request inherits whatever
  prefix the page itself was served under.
- The server's route table is unchanged: absolute is what arrives on the wire either way.
- On loopback the two forms are indistinguishable and the page behaves exactly as before.
- A test asserts the property rather than the spelling, and asserts that every relative reference
  still names a route the server serves.
- No listener moves off loopback. This is preparation, not exposure.

## Result

Done, and it turned out to be the one thing a proxy could not have fixed for us.

### Why path rewriting is not enough

`prefix_rewrite` — Envoy's, Caddy's, anyone's — repairs the request path *on its way upstream*. It
cannot repair a URL the browser has already constructed. A page served at `https://host/<nonce>/`
that fetches `/audio/bass` makes the browser resolve that against the **origin root**, producing
`https://host/audio/bass`, which never carries the prefix and so never matches the route that would
have rewritten it. The proxy sees a request for a path it has no route for, and the correct
behaviour — no default route — turns every stem into a 404.

`audio/bass` resolves against the page's own directory instead, so it inherits the prefix for free
and the server behind it stays unaware one exists.

### What changed

A shared `page_url()` in `observatory.py`, applied where a page's own references are built in both
observatories. The server's whitelist keeps the absolute form, because that is what arrives on the
wire either way: relative is how the page *asks*, absolute is what is *received*.

On loopback the two are indistinguishable, so this is a no-op for every current use — confirmed by
driving the page in a browser: four tracks indexed, five buffers decoded, novelty loaded, and the
resolved request URLs identical to before.

The prefix case was exercised without a proxy by asking the loopback server for exactly what a
prefix-stripping proxy would forward. All seven artifacts answer 200.

### Not done, deliberately

No listener moved off loopback and no proxy was configured. This is preparation; the exposure
decision is Henry's and needs him at the keyboard.
