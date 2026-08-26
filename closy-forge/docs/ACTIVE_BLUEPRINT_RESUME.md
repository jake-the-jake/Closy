# Active Blueprint Resume

This is the recoverable checkpoint for continuous Closy master-blueprint execution. It records
literal evidence only; green CI does not by itself promote a global blueprint gate.

## Current State

- Active checkpoint: `D0-FIDELITY-CLOSEOUT-BP52-BP53-BP47`.
- Branch: `codex/closy-forge-d0-fidelity-closeout`, stacked on the exact green Phase 6 head
  `a8d6500639e1aa662ef95c10754c618f12f42e10` from PR #7.
- Frozen Phase 6 final-head CI: run `32913193640`; Ubuntu and Windows passed. PR #7 remains
  draft and targets `codex/closy-forge-phase-5-provider`.
- The active branch implements BP52 bounded fit refinement, BP53 decoded bitmap/PBR evidence
  and BP47 independent decoded source-versus-render fidelity in the required order.
- Unrelated app edits in `metro.config.js` and `src/features/avatar-*` remain unstaged and must
  be preserved. `closy-forge/.tmp/` contains untracked local evidence only.

## D0 Fidelity Closeout

### BP52 Fitting

- `closy.tshirt_image_conditioned_fit.d0_iterative_v2` runs bounded coordinate descent over
  eight parameters using decoded masks, landmarks, camera metadata, dimensions and confidence.
- It evaluates 33 candidates, records 17 history entries and accepts eight improving moves.
- The objective improves from `0.092928787` to `0.009143346`, a relative improvement of
  `0.901609111`.
- Final bounded metrics include silhouette IoU `0.983152`, boundary error `0.001386632`,
  landmark RMS `0.003468` and opening alignment error `0.002106`.
- The selected winner is rebuilt, run through the full
  `closy.reference_xpbd_cpu.v1.3_integrated_self_collision_d0` solver and independently
  CPU-raster compared. The settled state content hash is
  `04bcaa7a862d2fde059a2d8b7c3418151d040ac492f52b16b3e20d9e09d71378`.
- Bounded uncertainty alternatives and camera/mask/landmark corruption controls are persisted
  and validated fail-closed.

### BP53 Decoded Bitmap/PBR Evidence

- Four project-authored public fixture PNGs are packaged as decoded source bytes and validated
  through the deterministic RGBA8 sRGB codec. ICC profile surprises are rejected.
- Eight real atlas PNGs are persisted: base color, derived normal, roughness, occlusion,
  view confidence, generated-region mask, source-contribution map and logo-region mask.
- The atlas records source-observed fraction `0.659362793`, controlled generated-fill fraction
  `0.340637207`, zero reported seam discontinuity and 432 protected logo-region pixels.
- Visible source evidence cannot be overwritten by controlled fill. Swapped source, wrong
  profile, shifted logo, seam discontinuity, corrupt bytes, wrong dimensions, forged confidence
  and provenance mismatch are rejected from persisted bytes.
- The derived normal/roughness/occlusion maps are D0 approximations, not measured fabric
  calibration. Legacy JSON map summaries remain explicitly labelled as summaries.

### BP47 Source-Render Fidelity

- `reports/fidelity/source_render_fidelity.json` compares four decoded source views with
  independent deterministic CPU renders of the fitted, settled garment.
- All four required views are nonblank and pass the bounded public-fixture D0 tier.
- Aggregate evidence records mean silhouette IoU `0.347457878`, maximum boundary Chamfer
  `0.051886302`, mean linear-sRGB MAE `0.024247878` and front/rear appearance delta
  `0.011240653`.
- Front source/logo comparison is mandatory. Nine persisted-byte corruption controls are
  detected, including detached-seam and source/logo corruption.
- `acceptedForD0PublicFixture=true`; private capture, provider appearance and signed human review
  remain `not_run`; clean/canonical acceptance remains false.

## Current Local Validation

- Canonical integration package builds with 125 manifest-inventoried files and digest
  `5ea83813e59fc07bc053ace3af9702f781893f9475ca8916d2612be1814173fa`.
- Validation counts are `info=0`, `warning=1`, `error=0`, `fatal=0`; the sole formal warning is
  `self_collision_unresolved_contacts`.
- Ruff passes, strict mypy passes over 100 source files and 55 schemas are freshly exported.
- The uninterrupted full suite passes all 234 collected tests, including the complete 95-test
  corruption module and the BP52, BP53, BP47, inspection, integration and golden coverage.
- Two independent release-style builds each contain 129 physical files and 125
  manifest-inventoried files. Their package trees are byte-identical and both have digest
  `5ea83813e59fc07bc053ace3af9702f781893f9475ca8916d2612be1814173fa`.
- Both packages validate with `info=0`, `warning=1`, `error=0`, `fatal=0`; the sole formal warning
  is `self_collision_unresolved_contacts`.

## Truthful Limits

- Gate C3 and Phases 3, 4 and 6 remain partial globally. D0 public-fixture acceptance is not
  product, clean-geometry or canonical acceptance.
- No private-user imagery, learned inverse fitting, provider-generated production shell,
  provider appearance review, authorised human review, measured real-fabric PBR calibration,
  mobile/GPU evidence, continuous collision detection or ZeroOne execution has run.
- The project-authored PNG fixture is public/synthetic evidence. It must not be described as a
  real customer capture or private-data proof.
- Main is visibly unprotected. This is a repository-governance warning, not permission to push
  or merge to main.

## Next Exact Command

```powershell
cd E:\apps\Closy
git add -u -- closy-forge
```

## Next Safe Action

Commit only `closy-forge` changes, push this branch, open a draft PR targeting
`codex/closy-forge-phase-6-binding`, wait for Ubuntu/Windows CI and apply at most one bounded
evidence-sync commit. Then branch `codex/closy-forge-phase-7-material-physics` from the exact
green D0 head and continue without stopping.
