# Provenance

Every artifact this project produces must be attributable. The test is a set of questions that a
provenance record has to answer about any file in `.work/`, `outputs/`, or `corpus/derived/`,
months later, with the code having moved on:

1. **Which input produced this artifact?**
2. **Which model or tool, at which exact revision?**
3. **With which parameters?**
4. **On which runtime and backend?**
5. **How long did it take?**
6. **What artifact hashes were emitted?**
7. **Is this observed, inferred, requested, or human-corrected?**

An artifact whose provenance cannot answer all seven is not evidence of anything. It is a file.

## The envelope

`spectral_loom.contracts.Provenance` is that record, and a `SongTimeline` carries a list of them —
one per producing stage, in production order.

```json
{
  "stage": "separation",
  "tool": "demucs",
  "tool_revision": "4.0.1+a1b2c3d",
  "truth_layer": "inferred",
  "input_hashes": { "source": "sha256:…" },
  "parameters": { "model": "htdemucs", "shifts": 1, "segment": 10 },
  "output_hashes": { "stems/bass.wav": "sha256:…", "stems/drums.wav": "sha256:…" },
  "runtime": "cpython3.11 macos-arm64 mps",
  "started_at": "2026-08-20T12:00:00Z",
  "duration_ms": 41230
}
```

Field by field, against the seven questions:

- `input_hashes` answers (1), by content rather than by path. A path is a claim about where a
  file was; a hash is a claim about what it contained, and only the second survives a move.
- `tool` and `tool_revision` answer (2). A revision is a version *plus* a commit where one is
  available. A bare version number is not a revision, and a branch name is not a revision at all.
- `parameters` answers (3), and carries only what affected the result — which is the same set
  that belongs in the cache key.
- `runtime` answers (4). It matters more than it looks: the same model at the same revision can
  produce different floating-point output on MPS and on CPU, and a result that cannot name its
  backend cannot be compared with another run.
- `duration_ms` answers (5), and is what makes it possible to notice that a cache is not being hit.
- `output_hashes` answers (6), and is what lets a later stage assert that it consumed exactly what
  an earlier stage produced.
- `truth_layer` answers (7). See [architecture.md](architecture.md).

## The one exception, and where its answers live

The three analysis stages inside a `song.timeline.json` — `activity.measure`,
`activity.interval`, `onset.spectral_flux` — answer questions 1, 2, 3 and 7 in the document and
deliberately do **not** answer 4, 5 and 6 there. This is the only exception in the project, and it
is a trade rather than an oversight.

**Questions 4 and 5 are omitted to buy something better than they give.** `started_at` and
`duration_ms` are precisely the two fields that would make the document different every time it was
produced from identical inputs, and gate 4 requires the opposite. `runtime` is omitted for a
stronger reason: leaving it out means two people on different machines compiling the same accepted
stems with the same parameters get **byte-identical documents**, so a timeline is a function of its
inputs rather than of who ran it and can be verified by recomputation rather than by trust. That is
worth more than knowing which laptop was warm.

**Question 6 has no answer at this level at all.** An analysis stage emits no file of its own — it
emits events *into* the document — and a document cannot contain its own hash.

All three answers exist; they live in a **build receipt** written beside the timeline as
`compile-receipt.json`. It records `started_at`, `duration_ms`, `runtime`, the timeline's own
sha256, the cache key and everything the key was computed from, and both human reviews that had to
match before the compile was allowed to start. The receipt names the timeline; the timeline does not
name the receipt, because a path inside the document would be a claim about where a file was rather
than what it contained.

The receipt is deliberately **not** one of the published contracts under `schemas/`. That directory
is the language-neutral surface another implementation reads; a local build record is not part of
the compiler boundary and should not look like it is.

The rule the seven questions state is unchanged: an artifact whose provenance cannot answer all
seven is not evidence. What changed is where two of the answers are written down, and that split is
mechanically enforced — `tests/test_timeline.py` asserts that every stage answers 1, 2, 3 and 7 in
the document, that the analysis stages carry no clock, and that the receipt answers the rest.

## Provenance is the cache key

These are not two mechanisms. A stage's cache key is the hash of its `input_hashes`, its `tool`,
its `tool_revision`, and its `parameters`. If any of those four change, the cached artifact is for
a different question, and reusing it is a correctness bug rather than an optimization.

Two consequences follow:

- **A stage that cannot enumerate its parameters cannot be cached.** Discovering a hidden
  parameter — a default that changed upstream, an environment variable read at import time — is a
  cache-invalidation event, not a footnote.
- **`duration_ms` on a run that should have hit cache is a bug report.** It is the cheapest
  available signal that a key is unstable.

## Model assets

The same standard applies before inference starts. A future model bootstrap script must:

- **pin an exact repository or model revision** — a commit sha, never a moving branch and never a
  bare tag, since tags move;
- **be idempotent** — running it twice does the work once;
- **verify presence before fetching**, by published hash where one exists, and skip the download
  when it verifies;
- **record the license and provenance** of what it fetched, in a tracked manifest, since the
  weights themselves are untracked and the record is the only thing that survives a clean clone;
- **not execute arbitrary remote model code** — `trust_remote_code` and its equivalents stay off
  unless a written, reviewed reason says otherwise for a specific model at a specific revision.

None of these scripts exists yet. `scripts/README.md` states the contract so that the first one
is reviewed against it rather than inventing its own rules.

## Human corrections

A correction is a stage, not an edit. It gets its own provenance entry with
`truth_layer: corrected`, naming the human as the tool and the inference it overrides in
`input_hashes`. The inference stays in the document.

This is the expensive-looking choice and it is the only honest one: an oracle comparison (roadmap
gate 8) needs to know which values a model produced and which a human fixed, and a correction that
overwrites its input has destroyed exactly the measurement being attempted.
