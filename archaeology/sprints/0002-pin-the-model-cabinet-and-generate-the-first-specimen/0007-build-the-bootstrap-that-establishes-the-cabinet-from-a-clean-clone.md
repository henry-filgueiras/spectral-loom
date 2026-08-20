---
id: tsk_01M0GK89WMD1DQ4J6N41SWWZX8
sequence: 7
kind: task
status: closed
sprint: spr_01M0GK725M1JMHQH8PQVSMGS7Q
created: 2026-08-20
closed: 2026-08-20
---

# Build the bootstrap that establishes the cabinet from a clean clone

## Objective

Write the first operational bootstrap under `scripts/`, to the contract `scripts/README.md`
already states, so that a clean clone can deliberately establish the local cabinet.

Its shape follows from the environment structure task:6 measures, not from a preference.

## Acceptance criteria

- Every requirement in `scripts/README.md`: exact immutable revisions, idempotent, verify before
  fetching, skip what already verifies, recover from a partial download, license and provenance
  recorded in tracked metadata, no arbitrary remote model code, writes only into ignored paths,
  human-invoked and never reached by a test or by CI.
- Idempotency demonstrated by measurement: run it, run it again, and prove from the second run
  that nothing was re-downloaded. Reading the code and concluding it skips is not evidence.
- The decisions the script makes — parsing the manifest, judging whether an asset verifies,
  computing paths — refactored into the package where that buys hermetic tests, and tested there.
- No test in the default suite touches the network or needs weights.

## Result

Done. `scripts/bootstrap_cabinet.py`, with `env`, `assets`, and `status`. Two subcommands rather
than two scripts because the halves are one act with one manifest: an implementation without its
weights runs nothing.

**Idempotency was measured, not asserted.** The evidence, in order:

- **Run 1**, cold: fetched 11,101,507,113 bytes of ACE-Step in 453.5 s and 84,039,727 bytes of
  HTDemucs in 6.7 s, then verified every file against the sha256 the hub publishes.
- **Run 2**, with `PYTHONPATH` injecting a `sitecustomize.py` that replaces `socket.socket.connect`
  with a function that raises, plus `HF_HUB_OFFLINE=1` and the `--offline` flag: exit 0, both
  assets reported `verified`, 26 files re-hashed in 3.9 s, `skipped, nothing downloaded`. A
  process that cannot open a socket completed successfully, which is a stronger statement than any
  log line about cache hits.
- **Negative control**, same socket guard against an empty models root: `NetworkAccessError:
  outbound connection attempted to ('huggingface.co', 443)`. The guard is live, so run 2's silence
  means silence rather than a broken blocker.

That third step is the one worth keeping as a habit. A guard that never fires is indistinguishable
from a guard that does not work.

**Against the `scripts/README.md` contract**, point by point: revisions come from the manifest and
its contract rejects anything but forty hex digits, with no flag to bypass it; verification happens
*before* `huggingface_hub` is imported, so a verifying asset costs no network call at all; partial
downloads resume rather than restart; license and provenance live in the tracked
`model-cabinet.toml` while the `.spectral-loom-fetched.json` beside the weights is only a local
receipt; `trust_remote_code` appears nowhere and no pinned repository contains a `.py`; everything
written lands under `models/` or `.venv-cabinet/`; and nothing in the suite executes the script.

**A deliberate refusal.** Files that are present but do not match what is pinned stop the fetch
instead of being overwritten. Wrong bytes are evidence about something — a truncated download, a
tampered mirror, a re-pin nobody finished — and a script does not get to destroy them on a machine
it does not own. It says which files and where, and stops.

**What was refactored into the package and tested.** `spectral_loom.cabinet` holds the manifest
contract, the path calculation, and `check_asset`, which returns five distinct states rather than a
boolean: `absent`, `incomplete`, `present`, `verified`, `corrupt`. `present` and `verified` are
kept apart because hashing 11 GB is affordable in a bootstrap and not in a `doctor`, and because
only a hashed report may authorise skipping a fetch. The case that motivates all of it — a file of
exactly the right length containing the wrong bytes — is a test, forged in `tmp_path` in three
lines, with no network and no weights.

The module is stdlib-only on purpose: `doctor` reads the cabinet from an environment that contains
none of it, and `assets` has to be able to report what is missing before the thing that fetches it
is importable.
