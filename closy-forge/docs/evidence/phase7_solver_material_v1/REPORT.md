# Phase 7 solver/material V1 retrospective closeout

This is a contaminated retrospective engineering evaluation of same-author, closely aligned
scalar one-dimensional numerical chains. It is not XPBD, material-physics, blind, predictive,
calibrated, or real-fabric evidence.

## Canonical outcome

- Engineering acceptance: `failed`.
- Scientific qualification: `ineligible_test_exposed_before_estimator`.
- First unmet predicate: `meanSixFieldNormalizedError`.
- Mean six-field normalized error: `0.4408391`.
- Nearest-rank P95: `0.790029586`.
- Worst six-field error: `0.84568`.
- Mean historical `predictiveNrmse`: `0.342844848`; this is
  fitted-observation reconstruction, not withheld prediction.
- Passing tuples: `0/16`.
- Result digest: `2e54ee3eaa80bc686c86d44c844cb6b63ac3ff24500999dca937d48d1d1c6e4d`.

Terminal conservation is 96 estimated + 32 abstained + 16 unsupported = 144 cells, with zero dropped
rows. Friction and restitution are abstained. Compression/thickness is unsupported. Confidence
intervals and frozen negative controls were not run. `real_coupon_count=0`;
`real_fabric_calibration=not_run`.

## Post-hoc diagnostics

All diagnostics are `post_hoc_non_qualification` and cannot alter the terminal result.
Independent checks found contact-control and inclined-contact state/observable diagnostics
equivalent across 64 rows,
64/64 vertical-drop rows
with zero contacts, 2 distinct friction responses,
and 1 distinct restitution response. The
two-configuration comparison changed node count, timestep, step count, and iteration count
together; it is not a convergence proof. Relative differences span
0.017545621 to 0.770528135 with mean
0.297045785.
