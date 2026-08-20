---
id: tsk_01M0GH7R5C7R63HZB2DEDPV7WE
sequence: 3
kind: task
status: closed
sprint: spr_01M0GH70AX635WAS8M3SQQRV9W
created: 2026-08-20
closed: 2026-08-20
---

# Ship the infrastructure-only validation CLI

## Objective

Ship the infrastructure-only `spectral-loom` CLI: `doctor`, `validate-spec`, `validate-timeline`.
Nothing that downloads, generates, or infers.

## Acceptance criteria

- `doctor` reports OS and architecture, Python version, Apple chip and unified memory on macOS,
  ffmpeg presence and version, uv presence, repository path, and writable cache/output locations.
- Absent future model dependencies are reported as informational and do not change the exit code.
- `doctor --json` emits machine-readable output.
- Validation commands print errors that name the offending field and path, and exit with stable
  documented codes: 0 valid, 2 invalid document, 3 unreadable input.
- Tests cover help, doctor in both modes, a valid spec, a valid timeline, and malformed input.

## Result

Done. Three commands, no fourth: `doctor`, `validate-spec`, `validate-timeline`.

**Exit codes are the interface**: 0 ok, 1 blocked, 2 invalid document, 3 unreadable input, all
stated in `--help` and tested. Separating 2 from 3 matters — a missing file and a malformed
document are different problems for a caller, and collapsing them into 1 would make a script
unable to tell a typo from a contract violation.

**`doctor` reports and does not act.** Writability is probed with `os.access` on the nearest
existing ancestor rather than by creating the directory, and a test asserts that running
`collect_checks` against a temporary directory leaves its contents unchanged. It reports OS,
architecture, macOS version, Apple chip and core count, unified memory, Python version and
interpreter path, `uv`, `ffmpeg`, the repository root, and three writable locations.

**Absent model dependencies are `info`, and `info` never changes the exit code.** `torch`,
`demucs`, `basic_pitch`, and `acestep` are probed with `importlib.util.find_spec`, which does not
import them. This is the concrete form of the rule in [[dec_01M0GH551CZF4QBEVQZYB391XF|Keep heavyweight model dependencies out of the default environment]]: bootstrap health and
inference readiness are different questions and must not share an exit code.

**Errors name the field.** Pydantic errors are rendered as `path.to.field: message`, one per line
on stderr, and JSON parse failures carry line and column. `--json` is available on all three
commands, and a failure payload carries its own exit code.

Measured on the bootstrap host: `doctor` reports Apple M5 Pro, 18 cores, 24 GiB unified memory,
ffmpeg 8.1, Python 3.11.16, and four absent model packages, exiting 0.
