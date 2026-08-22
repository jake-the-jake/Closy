# Capture Records v1

Phase 2 introduces canonical capture evidence without accepting real user photos yet.

The current fixture writes:

- `source/capture_record.json`
- `source/capture_quality.json`
- `source/visual_observations.json`
- `source/correction_record.json`
- `reports/capture_quality.json`
- `reports/visual_understanding_quality.json`

These records are deterministic, synthetic, metadata-only fixtures. They contain camera/view
metadata, visibility expectations, quality measurements, analytic polygon silhouettes, T-shirt
landmark observations, and an empty correction ledger, but no raster imagery, no body scans, no
personal measurements, and no provider output.

## Privacy Contract

The fixture must keep these fields false:

- `containsUserImagery`
- `containsPersonalBodyData`
- `allowExternalApis`
- `allowTrainingUse`
- `runtimeExternalApis`

The deletion policy is `regenerable_fixture_no_user_data` because the record can be recreated from
checked-in deterministic code. Future real capture ingestion must add consent, retention and
deletion records before real user media can become package input.

## Immutability

`capture_record.json` stores `immutability.sourceRecordHash`. The hash is computed from the
canonical JSON payload with that hash field blanked, so changes to camera metadata, privacy flags,
view measurements or visibility records invalidate the record.

The package inventory also hashes the full JSON files. This gives two useful checks:

- payload immutability for source-record semantics;
- package file integrity for the `.closygarment` container.

## Quality Scoring

`source/capture_quality.json` is produced by `closy.capture_quality_scorer.v1`. The scorer is
deliberately simple and deterministic. It scores:

- garment coverage;
- focus/sharpness;
- exposure reliability;
- background separation;
- occlusion safety;
- semantic landmark coverage;
- scale observability;
- view diversity.

The current fixture has four synthetic metadata-only views and passes with score `0.942650`.

## Visual Observations And Corrections

`source/visual_observations.json` stores provider-free analytic placeholders for the visual
understanding layer:

- one editable target-garment polygon mask per synthetic view;
- required T-shirt landmarks such as neck, shoulders, armholes, cuffs and hem points;
- normalized image coordinates in top-left origin `[0, 1]` space;
- confidence values that are intentionally separate from semantic/pattern certainty.

`source/correction_record.json` starts as `empty_editable_baseline` with no operations. It records
the allowed future edits, including mask polygon edits, landmark moves, semantic label overrides and
confidence overrides. Future real correction flows must append operations instead of rewriting
source evidence silently.

## Current Limitations

This is not learned image understanding yet. The masks and landmarks are synthetic placeholders used
to prove package shape, provenance and validation. Later stages must replace them with real
front/rear ingestion, provider or manual mask evidence, landmark observations, texture projection
evidence and human correction operations.

## Fitting Handoff

`fitting/tshirt_fit.json` consumes `source/visual_observations.json` and stores the first bounded
closed-form T-shirt parameter estimate. This is still synthetic and deterministic, but it proves the
next boundary: fit reports must cite the visual-observation hash, stay inside the authored T-shirt
parameter bounds, report losses, and provide explicit alternative hypotheses.
