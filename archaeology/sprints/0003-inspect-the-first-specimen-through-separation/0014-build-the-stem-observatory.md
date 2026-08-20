---
id: tsk_01M0GPWWCFFBTQSC3PKFSF3KXA
sequence: 14
kind: task
status: pending
sprint: spr_01M0GPVMBCYCX68KZF76QFQ5QS
created: 2026-08-20
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
