# Capture Records v1

Phase 2 introduces canonical capture evidence without accepting real user photos yet.

The current fixture writes:

- `source/capture_record.json`
- `source/capture_quality.json`
- `reports/capture_quality.json`

These records are deterministic, synthetic, metadata-only fixtures. They contain camera/view
metadata, visibility expectations, and quality measurements, but no raster imagery, no masks, no
body scans, no personal measurements, and no provider output.

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

## Current Limitations

This is not image understanding yet. It is the contract and validation substrate for later source
images, editable masks, landmark observations, texture projection evidence and human corrections.
