---
id: dec_01M0GMX87ZYNWN1GZR782RR20X
sequence: 9
kind: decision
status: accepted
created: 2026-08-20
---

# Restrict the lockfile to Apple silicon and Linux, and say so

## Context

Attempting the cabinet as an optional dependency group failed to lock — not for macOS on Apple
silicon, where it resolves fine, but for an environment nobody in this project has:

```
No solution found when resolving dependencies for split
(markers: platform_machine == 'x86_64' and sys_platform == 'darwin'):
  Because demucs>=4.1.0 depends on torch{platform_machine == 'x86_64' and
  sys_platform == 'darwin'}>=2.1,<2.3 ...
```

demucs 4.1.0 caps torch below 2.3 specifically on Intel macOS, presumably because that is where
PyTorch stopped publishing wheels. `diffusers` needs torch ≥ 2.6. The two cannot both be satisfied
there, and `uv lock` locks for every platform in scope, so one unsatisfiable split makes the whole
lockfile unwritable — including for the platforms that do work.

There were three ways out: give up the optional group and manage a second environment by hand;
loosen a pin until the resolver stopped complaining; or say plainly which platforms this project
supports.

## Decision

**`tool.uv.environments` restricts the lockfile to `darwin/arm64` and `linux/x86_64`. Intel macOS
is not a supported platform for Spectral Loom.**

This is a narrowing of support and is written down as one rather than left as a resolver
accident. Apple silicon is the host this project targets — `dragons/0002` and the roadmap both
already assumed it — and Linux is what CI runs.

## Consequences

- `uv sync --locked` fails outright on an Intel Mac rather than installing something subtly wrong.
  That is the intended behaviour; a project that cannot run its own cabinet on a machine should
  say so at the resolver rather than at the third stage of a pipeline.
- The lockfile carries a resolution nobody here will install: on Linux, `basic-pitch`'s own markers
  pull TensorFlow 2.15 and numpy 1.26, where macOS gets coremltools and numpy 2.4. That is honest —
  both are real resolutions of the same declaration — but the Linux one is **unmeasured**. Nothing
  in this project has run the cabinet on Linux, and the manifest's `accelerator = "mps"` is a
  measurement about this host only.
- Adding a platform later is a lockfile change and a round of measurement, not a configuration
  tweak. It stays visible.
- The alternative that was not taken: relaxing `demucs==4.1.0` to something older that does not
  carry the Intel cap. Rejected because it would have chosen the separator this project runs on the
  machine it actually uses, in order to accommodate a machine it does not.
