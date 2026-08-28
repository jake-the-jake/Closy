# Phase 12 static runtime preparation

This source-only sibling implements the dependency-independent Phase 12 work permitted before
scoped Z2. It is candidate/preparatory evidence, not Phase 12 acceptance and not mobile evidence.

## Executed scope

- Managed `.closyruntime` publication with a conventional GLB, optional ZeroOne static artifact,
  optional candidate dynamic metadata, compressed pages, exact inventory, checksums, capability
  versions, platform profile, privacy-safe source link, explicit fallback order and a pre-baked pose.
- A fail-closed consumer validates the bounded manifest and exact tree before page decoding or asset
  allocation. It rejects traversal, links, hardlinks, duplicate authority, stale versions, corrupt
  chunks, decompression expansion and decoded-memory overflow.
- Selection exercises explicit dynamic-capability metadata, static, conventional, failure, offline
  and independently validated last-good behavior. No ZeroOne dynamic deformation is claimed.
- Persistent local deterministic transfer fixtures support interruption, process-style resume,
  out-of-order arrival and final aggregate validation. Wrong, duplicate, missing, stale and corrupt
  chunks fail closed; cache state has explicit managed eviction.
- Private source correlation uses a scoped keyed HMAC. Raw capture hashes remain only in the private
  registry. Withdrawal removes the raw mapping and unauthorized managed derivatives while retaining
  only explicitly authorized non-identifying garment output.

## Limits and blockers

Scoped Z2 is unavailable because refreshed scoped Z1 fails and PHY1 physical quality is failing.
Therefore this branch cannot be the post-Z2 Phase 12 integration branch and cannot promote dynamic
runtime acceptance. A later post-Z2 branch must cherry-pick reviewed unique commits with `-x`, record
the source-to-destination mapping and regenerate shared status.

The transport is a local deterministic fixture, not a production remote service. Battery, thermal,
physical-device memory, driver/GPU rendering, cellular transfer and background resume are not run.
No private capture leaves the local registry fixture, and no private-user or P1 claim is made.

## Reproduction

From `closy-forge`, with the pinned Python 3.11 environment active:

```text
python -m closy_forge schemas check --schema-dir schemas/v1
python -m ruff format --check src scripts tests
python -m ruff check src scripts tests
python -m mypy src
python -m pytest tests/unit/test_runtime_delivery.py tests/unit/test_runtime_privacy.py
python scripts/run_phase12_static_runtime_evidence.py --base-sha <sha> --evidence-anchor-sha <sha> --output docs/evidence/phase12_static_runtime_prep_v1.json
```

The evidence runner builds two independent packages and requires identical canonical manifests. It
then executes fallback selection, persistent transfer resume/reordering, aggregate validation and
privacy withdrawal using only project-authored local fixtures.
