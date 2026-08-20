---
id: tsk_01M0GH7R5C7R63HZB2DEDPV7WE
sequence: 3
kind: task
status: pending
sprint: spr_01M0GH70AX635WAS8M3SQQRV9W
created: 2026-08-20
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
