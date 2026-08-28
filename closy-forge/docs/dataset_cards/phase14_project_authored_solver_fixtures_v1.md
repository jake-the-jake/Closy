# Phase 14 project-authored solver-fixture dataset card

## Identity and permitted use

- Dataset version: `closy.phase14.solver_fixture_dataset.d0.v1`.
- Canonical dataset hash: `3adad8db4a5b9653fe78e19b941ff633b64520b56b14587ced376c3905035284`.
- Intended use: bounded CPU experiments for material-preset ranking and pre-solve failure warnings.
- Authority: none over final fit, collision, opening, strain, seam, or package validators.
- Licence/provenance: generated entirely by project-owned repository code and project-authored
  public numerical fixtures. No external, scraped, private-user, licensed-body, or real-fabric
  measurements are included.

## Construction

The corpus contains 96 scenario identities and four versioned material-preset candidates per
scenario, for 384 executed numerical fixture rows. Each fixture runs 180 deterministic scalar
settle steps. Inputs are copied and hash-frozen before solver execution; outputs are written under
`solverOutcome` and never re-enter the prediction feature map.

The frozen feature axis contains only decision-time quantities: program complexity, opening ratio,
seam density, avatar shoulder/hip ratios, motion amplitude, capture quality, initial penetration,
and authored material descriptor values. Names containing outcome, final, validator, convergence,
failure, target, residual, collapse, risk, or settled semantics are rejected.

## Splits

| Split | Scenarios | Candidate rows |
| --- | ---: | ---: |
| Train | 60 | 240 |
| Validation | 18 | 72 |
| Test | 18 | 72 |

Source, program, and avatar group identifiers are disjoint across all three splits. Garment
category semantics may recur, but identity groups do not. Means, scales, and OOD envelopes are fit
from the train rows only. The committed leakage audit includes empty group intersections, feature
snapshot hash verification, and a deliberate forbidden-feature negative fixture.

## Labels

The numerical fixture emits a continuous material quality score and six deterministic binary
labels: settle failure, collision nonconvergence, opening collapse, excessive strain, seam
continuity risk, and low capture quality. The labels are produced after the solver run. They are not
features. The fixture validators retain authority over the synthetic run even when a learned warning
disagrees.

## Limitations

- This is a scalar project-authored numerical fixture, not the production cloth solver.
- It is useful for model plumbing, leakage controls, fallback policy, and bounded comparison only.
- It does not establish real-fabric calibration, physical garment quality, mobile performance,
  private-user validity, human review, or generalisation outside the declared synthetic envelope.
- The broader visual-geometry foundation-model corpus remains not started.

Canonical rows are in `docs/evidence/phase14_solver_fixture_dataset_v1.json`. Regenerate them with
`PYTHONPATH=src python scripts/generate_phase14_bounded_model_evidence.py --root .`.
