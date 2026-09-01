# Generated Blueprint Status

Authority: `closy.blueprint_status_model.v16` at evidence anchor `d7b6e810477f169fea3a3cfca23c5ed99ba603b7`.

## Requirement Rows

- complete: 20
- partial: 63
- not started: 7
- discovery pending: 11
- total: 101

## Phases

- Phase 0: `complete`
- Phase 1: `partial`
- Phase 2: `partial`
- Phase 3: `partial`
- Phase 4: `partial`
- Phase 5: `partial`
- Phase 6: `partial`
- Phase 7: `partial`
- Phase 8: `partial`
- Phase 9: `partial`
- Phase 10: `partial`
- Phase 11: `partial`
- Phase 12: `partial`
- Phase 13: `partial`
- Phase 14: `partial`

## Scoped Gates

- C1: global `partial`, scoped `pass`
- C2: global `partial`, scoped `pass`
- C3-Binding-D0: global `partial`, scoped `pass`
- D0-DisjointTshirt-v1: global `partial`, scoped `benchmark_failed_fixed_inventory_unfinished`
- D0-DisjointTshirt-v2: global `partial`, scoped `attempted_integrity_error`
- LayerCollision-D0: global `partial`, scoped `pass`
- MT1-MechanicalReference-D0: global `partial`, scoped `pass`
- P1: global `discovery_pending`, scoped `not_run`
- PHY1-Neutral-SeamSupport-D0-v3: global `partial`, scoped `failed`
- PHY1-SingleLayer-D0: global `partial`, scoped `failed`
- PHY1-SingleLayer-D0-v2: global `partial`, scoped `failed`
- PHY1-Topology-Strategy2-D0-v4: global `partial`, scoped `outcome_M_strategy_microfixture_failed_no_candidate`
- ResearchPrototype-D0-matrix-v2: global `partial`, scoped `historical_superseded_9_pass_3_fail_3_not_run`
- ResearchPrototype-D0-matrix-v3-core: global `partial`, scoped `partial_6_pass_5_fail_0_not_run`
- ResearchPrototype-D0-matrix-v3-supplemental: global `partial`, scoped `2_pass_0_fail_2_not_run`
- TextureRerender-KnownTarget-v3: global `partial`, scoped `known_target_regression_pass_not_qualification`
- Z1: global `partial`, scoped `candidate_default_all_family_and_representative_pass`
- Z2: global `partial`, scoped `failed_compiled_single_lod_reference_pairing`
- Z3: global `discovery_pending`, scoped `not_run`
- Z4: global `discovery_pending`, scoped `not_run`
- Z5: global `discovery_pending`, scoped `not_run`
- Z6: global `discovery_pending`, scoped `not_run`
- Z7: global `discovery_pending`, scoped `not_run`
- Z8: global `discovery_pending`, scoped `not_run`

Compute profile, data provenance, execution profile, and gate scope are independent axes. C3-Binding-D0 passes only for its fixed-avatar D0 T-shirt profile; PHY1-SingleLayer-D0 and its opt-in topology-v2 experiment both fail their declared scopes. The exact-candidate seam/support-v3 neutral preflight also fails, so the full 11-state PHY1 replay, CCD, and solver-driven Z2 are not run. Topology v2 remains opt-in and is not runtime-exposed. Historical matrix v2 is superseded at 9 pass, 3 fail, and 3 not-run. Current matrix v3 reports core 6 pass, 5 fail, and 0 not-run, first unmet at D0-RP-03, plus supplemental 2 pass and 2 not-run. The separate Unit F known-target texture replay passes 34 of 34 predicates but does not promote D0-RP-07. Historical compiled dynamic ZeroOne pairing failed, while the separate clean analytic MT1 mechanical-reference profile passes without implying Z2 or physical cloth. Geometric LayerCollision-D0 passes only for the indexed synthetic two-garment surface profile and does not imply PHY1. No GPU, mobile, private-user, or human-review execution is claimed.
