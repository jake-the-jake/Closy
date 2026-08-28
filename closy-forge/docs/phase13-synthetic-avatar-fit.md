# Phase 13 project-authored synthetic avatar fit

This source-only sibling implements the dependency-independent D0 measurement and deterministic fit
scope permitted while dynamic and layer prerequisites remain blocked. It is not integrated
multilayer Phase 13 acceptance and contains no private-user or licensed-body evidence.

## Frozen capability

The capability suite contains 88 project-authored analytic bodies: one baseline, 20 scalar boundary
cases, 45 scalar-pair interactions, 20 scalar-plus-posture interactions and two posture cases. It
varies height, shoulder width, chest, waist, hips, arm/leg/torso length, two supported shape-depth
coefficients and upright/forward/backward posture. Ranges and fit thresholds are immutable constants
included in the evidence digest.

Each body provides sampled collision rings and landmarks. A separate geometry oracle measures those
samples without calling the fit implementation. A corruption test changes only collision geometry
and proves that the independent comparison fails.

## Deterministic fit

The scoped solver emits T-shirt and trouser parameters for chest, shoulder, neck, body/sleeve length,
front balance/depth, waist, hip, outseam, cuff and seat depth. Reports persist measurement authority,
confidence, correction operations, ease, opening placement, radial clearance, collision-body
linkage, project-authored provenance and a canonical fit digest.

All supported cases must pass exact independent measurement recovery, declared ease, radial body
clearance, opening placement and confidence gates. Ten physically expected parameter sensitivities
must be monotonic. Unsupported scalar and incoherent vertical extremes reject before fitting.

## Evidence boundary

This is project-authored synthetic D0 CPU evidence only. It does not execute simultaneous garments,
inter-garment collision, Phase 11 dynamic deformation, Phase 12 post-Z2 runtime integration, private
captures, P1, licensed bodies or human review. Global Phase 13 remains partial. Later integration must
reconcile this source-only commit onto the exact verified Phase 12 parent and then execute the real
multilayer suite.

## Reproduction

```text
python -m ruff format --check src scripts tests
python -m ruff check src scripts tests
python -m mypy src
python -m closy_forge schemas check --schema-dir schemas/v1
python -m pytest tests/unit/test_avatar_variation_fit.py tests/unit/test_schema_freshness.py
python scripts/run_phase13_synthetic_avatar_fit_evidence.py --base-sha <sha> --evidence-anchor-sha <sha> --output docs/evidence/phase13_synthetic_avatar_fit_v1.json
```

