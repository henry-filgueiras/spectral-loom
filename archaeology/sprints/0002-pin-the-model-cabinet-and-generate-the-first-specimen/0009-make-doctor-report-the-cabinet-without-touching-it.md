---
id: tsk_01M0GK8VW9S47B4AJ2SYRT9FDV
sequence: 9
kind: task
status: closed
sprint: spr_01M0GK725M1JMHQH8PQVSMGS7Q
created: 2026-08-20
closed: 2026-08-20
---

# Make doctor report the cabinet without touching it

## Objective

Teach `spectral-loom doctor` to report the cabinet now that the cabinet has a real pinned identity
and a real installation layout, while keeping it what it already is: an observer that changes
nothing.

## Acceptance criteria

- Distinguishes states that are genuinely different: an entry known and pinned in the manifest, a
  runtime environment present or missing, assets present or missing, assets verified or merely
  present, and backend availability where that is cheap to know.
- Never downloads, never writes, never imports a model to find out. A `doctor` that has to load
  eleven gigabytes to answer a question is not a doctor.
- Bootstrap health and inference readiness stay separate, as the CLI's exit codes already intend:
  an unstocked cabinet is information and exits zero.
- `--json` stays useful to a machine.
- Covered by hermetic tests that construct cabinet states on disk rather than requiring one.

## Result

Done. `doctor` now answers three questions it previously conflated, and keeps two claims apart that
are easy to merge.

The three questions: **is this entry pinned** (`cabinet`, `cabinet-code:*` naming the pinned
version), **is its implementation installed** (read out of `.venv-cabinet`'s distribution metadata,
never by importing), and **are its weights here** (`cabinet-assets:*`, with the repository, the
short revision, and the license in the line, because the weights are untracked and the report is
where the license has to survive).

The two claims: `present` says the right number of bytes is there; `verified` says they are the
right bytes. Only `--verify` produces the second, because hashing eleven gigabytes is not something
a person running `doctor` to check their checkout should pay for. An asset report produced without
hashing may never authorise skipping a fetch, and `needs_fetch` enforces that rather than trusting
the caller.

Nothing was allowed to leak in:

- **No import of a model to find out whether it is installed.** `importlib.metadata` reads the
  distribution metadata of an environment this process is not in. A `doctor` that loads eleven
  gigabytes to answer a question costs more than the question.
- **No download, no write.** A test snapshots every mtime under a temporary tree, runs
  `collect_checks(verify=True)`, and asserts nothing changed.
- **An empty cabinet is `info` and exits zero.** A fresh clone has a fully pinned, entirely empty
  cabinet, and that is not a problem with the clone. A manifest that will not parse *is* `fail` —
  that is a problem with the checkout.

One check was inverted on purpose. The old `model-dep:*` rows reported the future model packages as
absent-and-expected. There is now a single `default-env` row that reports absence as **ok** and
presence as a **warning**: decision:5 puts the cabinet in its own environment, so a torch that is
importable from `.venv` means something installed it there by accident, and nothing previously
would have noticed.

`accelerator` is reported as `info` and says what the manifest records, that it was measured with
torch 2.13.0, and that `doctor` did not measure it here. A backend `doctor` did not measure is not
a fact `doctor` gets to state.

Tested by building cabinet states on disk in `tmp_path` — pinned-and-empty, present, right-length
wrong-bytes, unparseable — rather than by requiring a stocked machine. A test that passes only
where eleven gigabytes already sit is a test of that machine.
