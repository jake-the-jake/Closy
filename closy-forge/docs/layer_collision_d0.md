# LayerCollision-D0 source-only CPU core

This sibling is based on exact verified PR28 head
`5538d8ca41ad86412d2a2ef5f0a0daa9984c0b72`. It implements the bounded inter-layer physical core
required before later integrated Phase 13 outfit acceptance. It does not depend on, replace, or
claim Phase 11 dynamic, Z2, Phase 12 runtime, or PHY1 acceptance.

The solver advances every declared layer in the same state/step loop. It projects the innermost
surface against the shared body radius, then resolves adjacent inter-garment contacts using
symmetric inverse-mass-weighted radial response. Broad and narrow phases are deterministic and
only adjacent declared layer pairs receive constraints, preventing bridges across unrelated layers.

The frozen capability manifest covers:

- top over lower garment;
- jacket over shirt;
- dress with an outer layer;
- the layered-asymmetric family semantics;
- lower-body stress;
- sleeve and underlying-garment interaction;
- an extreme supported body;
- a three-material layer stack;
- identical coincident layers;
- cyclic, missing-ID, reversed-order, and incompatible-opening rejection.

Each accepted case reports simultaneous execution, layer IDs/order/materials, contact count, maximum
depth, contact area, minimum separation, supplied-body clearance, radial strain, seam crack, opening
retention, order violations, bridge count, response displacement, and a full convergence trajectory.
An unexecuted solver can never produce an issue-free report.

## Executed result

- Capability manifest hash: `91b76b4ff9527fa0d4ecdbe585c92143f2668e1a7e141d9350fe39bdadb35aa4`.
- Suite hash: `873215bd21ceb67f9d43ce28faacef4646518811442b2944d3575072229f6064`.
- Accepted simultaneous cases: `9/9`; adversarial rejections: `4/4`.
- Maximum initial inter-layer depth: `0.00325 m`; maximum final depth and contacts: `0`.
- Minimum final inter-layer separation: `0.002 m`; minimum body clearance: `0.0032 m`.
- Maximum radial strain: `0.018018018018`; minimum opening retention: `0.981981981982`.
- Maximum final seam crack, layer-order violations, and bridge constraints: `0`.

The finite remediation campaign used both permitted strategies: bounded bidirectional projection,
then a coupled mass-weighted isotonic active-set projection for the three-layer stack. It used two
tuning trials in total, below the four-per-strategy cap. No threshold or capability case was removed.

This radial-shell CPU reference is intentionally bounded. It is not production cloth, visual
quality, integrated simultaneous-outfit acceptance, mobile/GPU evidence, or a claim that PHY1 has
passed. The future Phase 13 integration branch must cherry-pick only this sibling's unique commits
onto the exact post-Phase12 lineage and rerun dynamic, runtime, layer, package, and outfit evidence.
