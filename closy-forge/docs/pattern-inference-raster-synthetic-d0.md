# Raster-derived pattern inference synthetic D0

This lane is a bounded, project-authored synthetic experiment for the Phase 9 E1
capability. It does not replace the historical feature-prototype evidence and does
not establish real-photo, private-user, mobile, or production generalisation.

## Observable path

Every source identity is a real Phase 8 garment program. The program is compiled by
the existing family generator, rendered into front, rear, left-oblique, and
right-oblique PNG captures, and decoded by
`closy_forge.capture.raster_sources.decode_raster_fixture_pixels`. The unassisted
model consumes only pixel-derived observables and permitted camera yaw/pitch.
Generator identity, generator seed, target family, target parameters, panel count,
opening count, and correction deltas are not model features.

Oracle masks and fixture landmarks are not consumed by the unassisted track. The
assisted track is not run in this increment. The foreground observation used here is
a deterministic border-colour estimate from decoded pixels, not the renderer's
source mask.

## Corpus and split

The canonical corpus has 12 pre-augmentation source programs per each of the eight
predeclared families and four multiview captures per source. Eight source identities
per family train the model, two are validation-only, and two are test-only. Split
identity is a canonical program digest computed before augmentation. Validation
recomputes that identity and rejects deliberate overlap.

Shift records cover parameter regime, camera/mirroring, avatar/background proxy,
material, capture style, seed family, and occlusion. One renderer and one canonical
Phase 2 decoder exist, so renderer-family and capture-pipeline-implementation
holdouts are truthfully `not_run`; seed or mirror variants are not relabelled as
independent renderer implementations.

## Model and controls

The model is the corrected project-owned multitask linear softmax/regression
baseline. Preprocessing is fitted from training samples only. Its declared loss is
cross entropy plus `0.35 * parameter MSE` plus L2, and the same coefficient is in
the implemented gradient. Training is deterministic Python binary64 with canonical
weight rounding.

Canonical evaluation includes label-permutation, pixels-destroyed, metadata-only,
duplicate-hash, nuisance mutual-information, seed-allocation, and deterministic
bootstrap controls. A control must remain at or below the predeclared `0.25` top-1
ceiling for eight classes.

## Downstream truth

For one held-out source from every family, E1 execution decodes the raster, predicts
family and continuous controls, validates a template program, compiles the actual
pattern, runs the family package builder and reference settle, and independently
rerenders the candidate against the hidden target. Evidence binds model output,
program, pattern, package, settled state, and rerender hashes. `learnedFitRun` is true
only when an accepted learned prediction changes geometry relative to the default
template. Wrong or deferred predictions use an explicitly identified validated
fallback and cannot count as learned execution.

E2 remains `not_run`: a fixed template classifier/regressor is not constrained
structured pattern-program generation. Global Phase 9 remains `partial` regardless
of synthetic E1 results.

## Correction and privacy

The generated correction record exercises accept, reject, and high-level bounded
edits with deterministic rebuilding and source/model provenance. It is an automated
interaction, so human review remains `not_run`. Raw rasters and private seed records
are ephemeral, are not committed, and are never uploaded by this workflow.

## Reproduce

From `closy-forge`, generate evidence on a clean exact source head:

```bash
python scripts/generate_raster_phase9_evidence.py \
  --output docs/evidence/phase9_raster_synthetic_d0 \
  --closy-sha "$(git rev-parse HEAD)"
```

Regenerate in an isolated temporary directory and compare deterministic canonical
artifacts with the committed evidence:

```bash
python scripts/generate_raster_phase9_evidence.py \
  --output docs/evidence/phase9_raster_synthetic_d0 \
  --closy-sha "$(git rev-parse HEAD)" \
  --check
```

The scheduled/manual GitHub Actions lane uses Python 3.11 as the canonical numeric
reference. Other supported Python lanes validate behavior under the test suite; no
cross-platform byte-identity claim is made without a recorded exact comparison.
