---
id: dec_01M0GHZ70T3P07ZAMNCENVZQ9H
sequence: 6
kind: decision
status: accepted
created: 2026-08-20
---

# Be observed by WitnessGlass without vendoring it

## Context

Claude sessions in this repository are recorded by
[WitnessGlass](https://github.com/henry-filgueiras/witnessglass), a flight recorder for coding
agents. Recording is per-repository and opt-in, so this is a choice this project makes about
itself and is worth writing down here rather than being inferable only from a settings file.

WitnessGlass's own archaeology already documents what instrumenting an external project costs:
`scripts/arm.sh` is bound to the WitnessGlass checkout, and its committed example names the
binary through `${CLAUDE_PROJECT_DIR}`, which in an observed project points at a path that does
not exist. Its `logs/0001` records a previous external commissioning and the finding that the
external-project gap is entirely in *arming*, not in operating: once armed, the observed project
needs to know nothing at all.

## Decision

This repository is observed, and it holds no copy of the recorder.

- **No vendoring, copying, or submoduling.** WitnessGlass is an installed binary on `PATH`
  (`cargo install --path <checkout> --locked`). The only WitnessGlass-shaped thing in this tree is
  an inert hook configuration.
- **The hooks use the exec form with a bare `command: "witnessglass"`**, resolved on `PATH`, so
  the configuration carries no machine-specific path and is portable across checkouts. That
  `PATH` resolution works was measured upstream, not assumed.
- **Only the inert example is tracked** — `.claude/settings.witnessglass.example.json`, which
  Claude does not read. The active `.claude/settings.local.json` and the whole `.witnessglass/`
  directory are gitignored, mirroring what WitnessGlass expects of itself.
- **Recordings are never committed.** They are unredacted and are not safe to share.
- Recording covers all eight hook surfaces WitnessGlass adapts: `SessionStart`, `PreToolUse`,
  `PostToolUse`, `PostToolUseFailure`, `PermissionDenied`, `SubagentStart`, `SubagentStop`,
  `SessionEnd`.

## Consequences

- A clone of this repository records nothing until someone deliberately arms it, which is the
  intended default: recording is a choice each operator makes.
- Arming takes effect on the **next** session. The bootstrap session that armed it is not in any
  recording, and that is accepted rather than worked around — arming mid-session produces a
  partial recording with no session boundary.
- A recording identifies which session, but not which project, which commit, or which recorder
  build. That is an open question upstream, not something this project can fix from here, and it
  means a recording's meaning depends on the directory it sits in.
- The recorder is a passive observer: it returns no decision and cannot influence the session it
  records.
