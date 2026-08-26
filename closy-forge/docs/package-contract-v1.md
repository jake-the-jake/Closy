# Package Contract v1

Forge writes `.closygarment` as an inspectable directory, not a zip/container file.

## Required Tree

```text
manifest.json
provenance.json
source/capture_record.json
source/capture_quality.json
source/visual_observations.json
source/correction_record.json
source/public_fixture/front.png
source/public_fixture/back.png
source/public_fixture/left_three_quarter.png
source/public_fixture/right_three_quarter.png
fitting/tshirt_fit.json
textures/texture_identity.json
textures/bitmap_pbr_report.json
textures/atlas/base_color.png
textures/atlas/normal.png
textures/atlas/roughness.png
textures/atlas/occlusion.png
textures/atlas/view_confidence.png
textures/atlas/generated_region_mask.png
textures/atlas/source_contribution.png
textures/atlas/logo_region_mask.png
proposals/raw_geometry_proposal.json
proposals/manual_raw_visual_proposal.glb
proposals/manual_cleanup_preview.glb
proposals/clean_geometry_proposal.json
proposals/provider_registry.json
avatar/avatar_contract.json
avatar/reference_avatar.glb
avatar/collision.glb
avatar/body_regions.json
semantic/garment_graph.json
semantic/confidence.json
pattern/pattern.json
pattern/panels.svg
simulation/simulation_mesh.glb
simulation/mesh_manifest.json
simulation/constraints.json
simulation/rest_state.json
simulation/settled_state.json
simulation/settle_diagnostics.json
simulation/material_physics.json
simulation/material_presets.json
simulation/material_motion_states/*.json
simulation/motion_states/index.json
simulation/motion_states/*.json
render/fallback.glb
render/simulation_fallback.glb
render/simulation_fallback_manifest.json
render/mesh_manifest.json
render/materials.json
binding/sim_to_render.bin
binding/binding_manifest.json
binding/production_binding_contract.json
reports/avatar_quality.json
reports/capture_quality.json
reports/visual_understanding_quality.json
reports/fitting_quality.json
reports/texture_quality.json
reports/geometry_proposal_quality.json
reports/raw_geometry_topology.json
reports/provider_bakeoff.json
reports/geometry_cleanup_plan.json
reports/geometry_cleanup_result.json
reports/clean_geometry_proposal_quality.json
reports/provider_registry_quality.json
reports/semantic_quality.json
reports/pattern_quality.json
reports/simulation_quality.json
reports/render_quality.json
reports/binding_quality.json
reports/production_binding_c3.json
reports/self_collision_report.json
reports/material_selection.json
reports/material_calibration.json
reports/material_motion_suite.json
reports/fidelity/source_render_fidelity.json
reports/fidelity/*.png
reports/package_validation.json
reports/summary.json
reports/summary.md
```

Absent optional stages are omitted rather than represented by fake folders. The `source/` directory contains deterministic public/project-authored capture records, decoded visual evidence and four package source PNGs; those pixels are not private-user imagery. The `fitting/` directory contains a bounded iterative T-shirt fit that consumes decoded masks, landmarks, camera metadata and confidence, then verifies its selected winner through the full XPBD solver and an independent CPU raster. The `textures/` directory contains both legacy JSON summaries and eight actual decoded bitmap atlas/PBR/provenance maps. Source-observed and controlled generated regions remain explicitly separated; derived normal, roughness and occlusion maps are D0 approximations rather than measured fabric calibration. `reports/fidelity/source_render_fidelity.json` and its PNG artifacts compare four decoded source views with independently rendered settled geometry and accept only the bounded public-fixture D0 tier. Private, provider and human-review tiers remain not run, and clean/canonical acceptance remains false.

The `proposals/` directory contains a package-contained project-authored manual raw visual proposal GLB, a non-canonical cleanup preview GLB, an explicit rejected clean-geometry proposal report and a provider registry. `reports/raw_geometry_topology.json` records connected-component, boundary-edge, non-manifold and degenerate-triangle diagnostics for the raw GLB. `reports/provider_bakeoff.json` records the Phase 5 D0 provider comparison across the null adapter, selected manual fixture adapter and not-run local open-model boundary; it grants no clean/canonical authority. `binding/production_binding_contract.json` identifies one authoritative settled-simulation-to-subdivided-render route and deprecates contradictory legacy tracks. `simulation/motion_states/` stores eleven solver-produced source states. `render/simulation_fallback.glb` is the independent direct simulation-mesh fallback. `reports/production_binding_c3.json` reopens and recomputes all persisted assets; its status remains `partial_scoped_reference_profile`, because fallback landmark agreement and tangential seam sliding exceed provisional thresholds. `reports/self_collision_report.json` records integrated deterministic D0 collision projections, independent-oracle/adversarial fixtures, unresolved contacts and the explicit high-velocity tunnelling limitation. There is no private raster processing, learned segmentation/inverse-fitting model, `zeroone/`, accepted clean geometry proposal, external AI mesh execution or local open-model execution in this milestone.

Phase 7 material files contain four authored public-fixture descriptors, transparent preset
selection, six numerical sensitivity fixtures and four actual CPU T-shirt material states
reconstructed through the authoritative dense binding. Bounded execution and motion-quality
acceptance are separate: current opening drift and unresolved self-collision prevent motion-quality
acceptance. No measured real-fabric calibration, learned/private material inference or production
GPU material motion has run.

## Inventory Rules

The manifest inventory uses POSIX package-relative paths only. Absolute paths, `..`, Windows separators, escaping symlinks, undeclared canonical files, and manifest self-hash cycles are invalid.

`manifest.json` and mutable reader reports are excluded from the canonical package digest. All other canonical package files are hashed by SHA-256.

## Capabilities

`acceptedForD0MaterialPhysics` means descriptor, selector, fixture-calibration and bounded CPU
execution evidence is available; it does not mean material motion quality passed.

Capabilities are booleans, not quality scores. `settledRenderFitComparisonAvailable`, `decodedBitmapAtlasAvailable` and `sourceRenderFidelityAvailable` mean the bounded D0 package contains recomputable persisted-byte evidence. `acceptedForD0PublicFixture` does not imply private-image, provider, human, clean-geometry, canonical or production acceptance. `productionBindingC3EvidenceAvailable` means the package contains recomputable evidence; `productionBindingC3ProfileAvailable` remains false until every literal scoped threshold passes. External geometry providers, available clean geometry proposal, local open-model execution, personalised avatar, production GPU self-collision, global Phase 6 completion and ZeroOne states remain false. The rejected clean proposal, partial cleanup result, provider bake-off, D0 public fidelity report and partial C3 report are evidence that bounded gates were evaluated, not claims of canonical acceptance.

Host-dependent performance measurements are never canonical package files. The benchmark schema is exported as `schemas/v1/production-binding-benchmark.schema.json`; reports belong in local or CI run evidence and must include commit, host/runtime identity, warmups, repeats, dense/fallback timings, peak-memory method and limitations.

## Sleeveless-Top D0 Profile

The Phase 8 sleeveless profile is a smaller 41-file public fixture with its own manifest schema.
It contains exactly two torso panels, shoulder/side seams, and four semantic openings: neck, hem,
left armhole and right armhole. It does not retain empty sleeve or cuff IDs. Its profile-specific
files include:

```text
fitting/sleeveless_fit.json
simulation/material_selection.json
simulation/motion_states/{lightweight_knit,cotton_jersey,heavy_jersey,lightweight_woven,opening_stress}.json
textures/sleeveless_pbr_report.json
reports/sleeveless_quality.json
```

`render/fallback.glb` is reconstructed from the authoritative binary dense binding.
`render/simulation_fallback.glb` is independently written from settled simulation topology and
does not call dense reconstruction. Validation reopens all GLBs and binding bytes before
recomputing this relationship. The source views are project-authored pattern-boundary rasters;
the rendered views use an independent CPU triangle rasterizer. This is D0 public-fixture evidence,
not learned fitting, private-user reconstruction, measured fabric calibration, production GPU
cloth, or global Phase 8 completion.

## Long-Sleeved-Top D0 Profile

The Phase 8 long-sleeved profile uses the same shared 41-file contract shape while retaining
literal family semantics. Its four panels are front/back torso and left/right long sleeves. Ten
seams persist shoulder, side, split armhole and underarm attachments; its open boundaries are neck,
hem and two cuffs. Family-specific artifacts are:

```text
fitting/long_sleeved_fit.json
textures/long_sleeved_pbr_report.json
reports/long_sleeved_quality.json
```

The fixture executes four authored material presets, a cuff stress state, authoritative dense
binding and an independent simulation-topology fallback. It is deterministic public CPU evidence,
not private-user fit, measured fabric calibration, production GPU cloth or global Phase 8
completion.

## Simple-Skirt D0 Profile

The Phase 8 simple-skirt profile is a literal bottom garment in the shared 41-file contract. Its
front/back flared panels are joined by left/right side seams; waist and hem are the only semantic
openings. Family-specific artifacts are:

```text
fitting/simple_skirt_fit.json
textures/simple_skirt_pbr_report.json
reports/simple_skirt_quality.json
```

The fixture executes bounded waist/hip/length/flare fitting, four authored material presets, a
waist-opening stress state, authoritative dense binding, independent simulation-topology fallback,
decoded PBR and source/render fidelity. It is public synthetic CPU evidence, not private-user fit,
measured fabric calibration, production GPU cloth or global Phase 8 completion.

## Simple-Trousers D0 Profile

The Phase 8 simple-trousers profile is a literal four-panel bottom garment in the shared 41-file
contract. Front-left, front-right, back-left and back-right leg panels are joined by two outseams,
two inseams and front/back rise seams. The four waist edges form one semantic waist opening; each
front/back cuff pair forms a separate left or right leg opening. Family-specific artifacts are:

```text
fitting/simple_trousers_fit.json
textures/simple_trousers_pbr_report.json
reports/simple_trousers_quality.json
```

The fixture executes bounded waist/hip/outseam/cuff fitting, four authored material presets, a
two-cuff opening stress state, 1,092-record authoritative dense binding, independent
simulation-topology fallback, decoded PBR and composite two-panel source/render fidelity. It is
public synthetic CPU evidence, not private-user fit, measured fabric calibration, production GPU
cloth or global Phase 8 completion.

## Simple-Dress D0 Profile

The Phase 8 simple-dress profile is a literal four-panel one-piece garment in the shared 41-file
contract. Separate front/back bodices join separate front/back skirts at sewn waist seams; shoulder
and side seams leave one neck, one hem and two armhole openings. The waist is deliberately not an
opening. Its family-specific artifacts are:

```text
fitting/simple_dress_fit.json
textures/simple_dress_pbr_report.json
reports/simple_dress_quality.json
```

The authoritative dense shell is reconstructed only through `binding/sim_to_render.bin`; the direct
simulation fallback remains topologically independent. Completion is limited to the deterministic
public CPU fixture and does not imply private-user fitting, real-fabric calibration, production GPU
cloth or global Phase 8 acceptance.

## Button-Shirt D0 Profile

The Phase 8 button-shirt profile uses five literal panels: split left/right fronts, one back and two
long sleeves. Ten sewn shoulder/side/armhole/underarm seams intentionally exclude the front placket.
Neck, hem, placket and both cuffs remain semantic openings. Six ordered button/buttonhole records
pair opposite placket edges but are explicitly not simulated fastening constraints. Family-specific
artifacts are:

```text
fitting/button_shirt_fit.json
textures/button_shirt_pbr_report.json
reports/button_shirt_quality.json
```

The public fixture selects the authored lightweight-woven preset from disclosed categorical cues.
Its authoritative dense shell is reconstructed only through `binding/sim_to_render.bin`; the direct
simulation fallback remains topologically independent. This is deterministic public CPU evidence,
not button mechanics, private-user fitting, measured fabric, production GPU cloth or global Phase 8
acceptance.
