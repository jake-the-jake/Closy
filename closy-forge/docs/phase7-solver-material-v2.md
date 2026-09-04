# Phase 7 solver/material engineering V2

This increment is source-guarded, same-project synthetic engineering. It does not contain real coupon
measurements and cannot establish physical calibration, private-user readiness, mobile performance, or
product acceptance. Phase 7 therefore remains partial regardless of the synthetic terminal result.

V2 executes geometric coupon and garment meshes through
`closy.reference_xpbd_cpu.v2.0_material_coupled_d0`. The inherited distance update is XPBD: it computes
`alpha = compliance / dt^2`, applies `delta_lambda = (-C - alpha * lambda) / (w + alpha)`, accumulates
the multiplier across solver iterations, and resets it per substep. Support and contact are bounded
position projections, so the overall implementation is accurately described as an XPBD-centred hybrid.
No inherited V1 entry point or evidence identity is replaced.

All synthetic quantities use an explicit SI contract. The dimensional ranges are test protocol ranges,
not measured fabric claims. Locked targets are withheld behind commitments until the one canonical run;
the post-result disclosure is permanently exposed and ineligible for later selection.

The evaluated families are T-shirt, sleeveless top, and simple skirt. Each recovered descriptor drives
the same canonical settle and motion entry points used by package tooling. The retained proxy trajectories
cover silhouette, selected landmarks, hem/sleeve/neck displacement, drape, fold scale, temporal response,
penetration, collision, strain, seam residual, termination, performance, material identity, and provenance.

Real measurements may later be provided only through the strict `material-coupon` CSV interface. The
checked-in template contains headers and units only; the canonical real-coupon count remains zero.
