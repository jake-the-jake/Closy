# Phase 9 Learned Synthetic D0

This slice replaces the leaky 24-record lookup demonstration with an actual, bounded training and
evaluation route. It is deliberately scoped to project-authored synthetic captures. Global Phase 9
remains partial because no real/public capture corpus, private-user authority, production calibration,
or human-reviewed correction evidence exists.

## Reproduce

From `closy-forge/` with the pinned Python 3.11 environment:

```powershell
$env:PYTHONPATH = "src"
py -3.11 -m closy_forge pattern-inference train-synthetic-d0 `
  --output .tmp/phase9-learned-d0 `
  --commit-sha <exact-implementation-sha>
```

The command persists grammar, dataset, split, model weights, training curve, held-out evaluation,
dataset/model cards, licence/provenance, correction session, two-run reproducibility, and measured
host execution evidence. It also builds and validates held-out sleeveless-top and simple-skirt
`.closygarment` packages and reads their actual settled states, fit losses, decoded source/render
comparison, bounds, and canonical package digests. Host timings are non-canonical evidence and are
not mobile-performance claims.

## Grammar and compiler

`grammar_v2.py` represents panel nodes, boundary curves, seam spans/pairing/ease, openings, supported
shaping, material regions, layer order, fastenings, measurements/confidence, correction operations,
version, and provenance. The validator fails closed on missing spans, duplicate semantic IDs, seam
or layer cycles, invalid openings, non-simple panels, inconsistent ease, unsupported features, and
out-of-range family parameters.

Programs compile only by reconstructing a bounded family parameter object and invoking one of the
eight existing Closy pattern generators. A second pattern audit rechecks panel geometry and every
seam/opening reference. The learned route cannot publish arbitrary geometry around this compiler.

## Dataset and split

The deterministic dataset contains 96 independent garment programs and 384 capture variants across
all eight Phase 8 families. It varies measurements/proportions/ease, materials and layer families,
camera, mask and landmark noise, occlusion, colour/texture observations, and simulated correction
events. Thirty-two challenge fixtures cover ambiguous, negative, unsupported, and corrupted input.

Inputs contain only numeric capture-like observables. Family/template labels, panel/opening counts,
and exact target parameters are absent. The validator recursively rejects target-defining input keys.
Program groups, not observations, are split 256/64/64; the validator recomputes both group
disjointness and sample membership.

## Model and evaluation

The project-owned CPU model is a multiclass softmax linear classifier plus three continuous linear
regressors. Full-batch gradient descent optimizes the declared
`cross_entropy + 0.35 * parameter_mse + l2` loss with fixed seeds and no new dependency. Numerical
finite-difference tests cover classification and regression gradients. Canonical model JSON persists
normalization, learned weights, centroids, OOD policy, optimizer configuration, and training curve.

On 16 held-out program identities and 64 observations, the current deterministic fixture result is:

- family top-1/top-3: 64/64;
- valid grammar and seam/opening decodes: 64/64;
- OOD/challenge action accuracy: 30/32;
- continuous MAE: length scale `0.019518082`, width scale `0.021652209`, normalized ease
  `0.267459873`;
- two independently trained canonical model files: byte-identical;
- nearest-centroid template baseline family accuracy: 64/64.

Because the deterministic baseline also classifies all held-out synthetic families, this work makes
no learned-superiority claim. Continuous prediction, calibration, OOD deferral, grammar-safe decode,
and persisted optimization are the scoped learned contributions.

## Correction and rollback

The bounded correction artifact exposes only length, width, and ease controls. It records accepted
and rejected events, rebuilds through the grammar compiler, verifies a repeated pattern hash, and
preserves seed/model/event provenance. Every automated record says `simulated_fixture`; human review
remains `not_run`.

Rejected, corrupt, or out-of-domain captures use a deterministic nearest-training-centroid template
with default bounded parameters. Corrupt observations use the fixed safe template. This rollback is
always available and never converts a rejected learned result into learned evidence.

## Limits

- Project-authored synthetic fixtures are not evidence of real-camera generalisation.
- No private-user data is stored or used for training.
- No external dataset or model dependency was added.
- Settled-package evidence covers two D0 families, not all garments or production cloth fidelity.
- Host CPU runtime/memory is not mobile, GPU, battery, or thermal evidence.
- Automated correction fixtures are not human review.
