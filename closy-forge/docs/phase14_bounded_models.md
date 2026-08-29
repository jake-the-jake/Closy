# Phase 14 bounded material, failure, and quality models

This source-only sibling implements the dependency-independent portion of Phase 14. Its parent is
the exact verified prerequisite-reconciliation head
`5538d8ca41ad86412d2a2ef5f0a0daa9984c0b72`. It does not bypass the failed refreshed Z1, PHY1, Phase
11 dynamic, Z2, LayerCollision, or integrated Phase 13 gates.

## Implemented

- A deterministic project-authored numerical settle-fixture corpus with 384 executed candidate
  outcomes and source/program/avatar-group-disjoint splits.
- Hash-frozen prediction-time features and fail-closed leakage checks.
- Train-only preprocessing and OOD envelope fitting.
- A bounded ridge material-preset ranker that returns stiffness, compliance, damping, and thickness
  initialization priors with confidence/fallback behavior.
- A bounded multi-label logistic model for settle, collision, opening, strain, seam, and capture
  warnings.
- Deterministic preset and pre-solve rule baselines, held-out evaluation, calibration diagnostics,
  OOD rejection, and decision-utility comparison.
- Deterministic regeneration, model/dataset/evaluation hashes, rollback policy, cards, provenance,
  licences, resource limits, and known-failure records.

## Authority boundary

The models can rank, warn, or defer. They cannot accept a garment, suppress a contact, alter a
physical threshold, or override final deterministic validators. An OOD, corrupt, low-confidence,
or model-error result falls back to the versioned cotton-jersey preset and validator-only behavior.

## Not implemented

- Phase 11 compiled dynamic deformation and Z2 did not run because prerequisites do not pass.
- PHY1 is still a fail-closed physical failure.
- Phase 13 multilayer/private/P1/licensed/human tiers are not claimed.
- The Phase 9 structured pattern model was not expanded: its learned model did not establish
  superiority over the deterministic centroid baseline.
- Broader native visual-geometry model fine-tuning remains not started because authorised data,
  licences, weights, and compute are unavailable.

## Reproduction

From `closy-forge` with this worktree's `src` first on `PYTHONPATH`:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
python scripts/generate_phase14_bounded_model_evidence.py --root .
python -m pytest tests/unit/test_phase14_bounded_models.py -q
python -m mypy --strict src/closy_forge/bounded_models scripts/generate_phase14_bounded_model_evidence.py
python -m ruff check src/closy_forge/bounded_models scripts/generate_phase14_bounded_model_evidence.py tests/unit/test_phase14_bounded_models.py
python -m ruff format --check src/closy_forge/bounded_models scripts/generate_phase14_bounded_model_evidence.py tests/unit/test_phase14_bounded_models.py
```

Global Phase 14 remains partial.
