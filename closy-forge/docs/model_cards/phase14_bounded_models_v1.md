# Phase 14 bounded advisory models card

## Model identity

- Model version: `closy.phase14.bounded_advisory_models.d0.v1`.
- Canonical model hash: `79e1f40390f910617f690735f6dfe0be331d044e5b41d048f3d5870086f9cc20`.
- Weights hash: `02ffea5b86636d89762d66aad1aa22b11384b80502432caa6c2a250df300bd29`.
- Dataset hash: `3adad8db4a5b9653fe78e19b941ff633b64520b56b14587ced376c3905035284`.
- Intended use: rank a versioned material preset, initialize stiffness/compliance/damping/thickness,
  and issue pre-solve warnings or request a deterministic fallback.
- Prohibited use: replacing deterministic validators or asserting production physical quality.

## Training protocol

The campaign uses pure Python on CPU. Three fixed configurations jointly train a ridge material
quality ranker and six one-vs-rest logistic warning heads. Each logistic head runs 60 full-batch
epochs. The selected trial is chosen on the validation objective. This stays below the predeclared
budget of four trials, 80 epochs, 3,600 wall/CPU seconds, and 2 GiB memory.

Normalization and the rectangular OOD envelope are learned from train rows only. No test-time
calibration is fit. Reported sigmoid probabilities retain their measured Brier score and expected
calibration error rather than being presented as calibrated production probabilities.

## Held-out results

- Material ranking: top-1 `10/18` (`0.555556`).
- Learned mean selection regret: `0.002497041219`.
- Fixed cotton-jersey preset mean regret: `0.059508457823`.
- Material score mean absolute error: `0.059294404971`.
- Failure/quality macro-F1: `0.704125286478`.
- Macro Brier score: `0.078745612838`.
- Macro expected calibration error: `0.192325757454`.
- Learned warning decision utility: `0.338888888889`.
- Frozen deterministic rule utility: `-0.044444444444`.
- OOD challenge rejection: `32/32`; in-distribution acceptance: `72/72`.

The material model improves regret over the fixed preset but does not demonstrate universal model
superiority. Excessive-strain and seam-risk heads each have held-out F1 `0.4`; these are explicit
known weaknesses, not hidden passes.

## Runtime and rollback

Every prediction is advisory. Corrupt/nonfinite features, OOD values, a low ranking margin, or any
model error select `material.cotton_jersey_d0_v1` and return control to deterministic validators. A
validator rejection always wins over a model prediction. Persisted artifacts are small JSON weight
files and need no external runtime service.

## Known limitations

- Trained on project-authored synthetic scalar solver fixtures only.
- No real-fabric, private-user, provider, licensed-body, human-review, GPU, mobile, battery, or
  thermal evidence.
- No Phase 11 dynamic or Z2 integration, and PHY1 remains failing.
- No structured-pattern model extension was made in this lane.
- Broader visual-geometry-model fine-tuning remains not started.
