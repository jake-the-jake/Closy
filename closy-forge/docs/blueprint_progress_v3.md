# Blueprint Progress V3: PR66 Baseline

This is a **safe successor reporting entry point**, not a replacement for frozen evidence.
Baseline inspected locally on 2026-09-05: PR66, head
`930b3da556c96e9ded52b6ee8df5620d4903c280`, tree
`1aee06f2d65bd66a08c63e30ad47ceb65c85a590`. The source blueprint blob is
`b0b702ff940719a6c83a232487762077345090fd`.
The parent implementation owns the subsequent Unit A/B/C outcomes and updates to active-resume
pointers. **No new unit acceptance results are incorporated here.** No GitHub fetch, evaluation,
commit, push, source-lock change or old entry-point edit is performed by this sidecar.

The [master blueprint](Closy_AI_3D_Garment_and_ZeroOne_Integration_Master_Blueprint.md#17-phased-implementation-roadmap)
remains architectural authority. Older progress documents can contain stale PR59/PR60-era instructions
and contradictory historical phase assessments. Read those as dated inputs, not a newer frontier.

## Four Separate Questions

- **Implementation / CI:** working code exists across all 15 roadmap phases, with very different
  supported scopes. The supplied PR66 checkpoint reports 32/32 successful Forge checks and a skipped
  Supabase check. This sidecar did not independently requery GitHub or rerun that matrix.
- **Development quality:** PR63 capture, PR64 material recovery, PR65 manual-provider binding and PR66
  all-family static/runtime acceptance remain failed or partial. Passing checker tests can correctly
  preserve a failed quality result.
- **Scientific qualification:** no new qualification. Y2 remains
  `preseed_scientific_protocol_invalid`; Strategy 3 is consumed, topology-strategy budget is zero,
  canonical-candidate budget is one. PR62's ineligible retrospective result is not repaired here.
- **Product readiness:** no Research Prototype, global C3, PHY1, dynamic Z2, Alpha/Beta, physical fabric,
  physical mobile or production acceptance follows from this reporting work.

## Phase 0-14 Overview

These are editorial assessments grounded in inspected code and saved artifacts, not automatically
propagated statuses for every source requirement. Phase 0 retains its historical *fixture-scoped*
implementation rather than being downgraded to absent; its acceptance is not reassessed here.
Phases 1-14 remain partial at their full blueprint scope.

| Phase | Inspected implementation and supported scope | Saved evidence / unmet gates | Dependencies |
|---|---|---|---|
| 0: Contract/harness | [T-shirt pipeline](../src/closy_forge/pipeline/build_tshirt_demo.py) joins package IO, hashes, validation, CLI and deterministic fixture assets. | [101-row ledger](blueprint_coverage.json) historically calls Phase 0 complete in its bounded fixture scope; no fresh acceptance run here. | Preserve versioned fixture identity; review actual command/check receipts before broadening scope. |
| 1: T-shirt construction | Same pipeline builds panels, seams, simulation/render meshes, settling and conventional GLB. | [PR66 result](evidence/static_zeroone_runtime_v2/result.json) includes valid T-shirt static/runtime output, not general physical drape proof. | Independent physical convergence, seams and body-clearance acceptance. |
| 2: Capture | [Pixel contestant](../src/closy_forge/capture_reconstruction_v2/contestant.py) decodes images/video and extracts observations; camera/correction modules exist. | [PR63](evidence/capture_reconstruction_v2/canonical_result_envelope.json): 30 synthetic sessions decoded, 28 fitted/intrinsically valid, two QC rejects; zero route eligible; first failure `CAPV2-05`. | Better inference, authorized imagery and P1 before private captures. |
| 3: Image fitting | [Fitter](../src/closy_forge/capture_reconstruction_v2/fitter.py) estimates bounded structured parameters, compiles and settles T-shirt/sleeveless/skirt. | [PR63](evidence/capture_reconstruction_v2/canonical_result_envelope.json): 28 intrinsic packages fail physical quality; fitted code is not absent, but route acceptance failed. | Reliable camera/body estimates and image-to-drape fidelity. Known generator parameters do not prove image inference. |
| 4: Appearance | [Projection and controls](../src/closy_forge/capture_reconstruction_v2/appearance.py) use fitted camera/geometry and observed pixels. | [PR63](evidence/capture_reconstruction_v2/canonical_result_envelope.json): 123/150 causal appearance controls pass; general texture/PBR fidelity is not accepted. | Reliable geometry/cameras, real-logo preservation and independent human visual review. |
| 5: Providers | [Manual package path](../src/closy_forge/manual_provider_c3_v1/package.py) retains raw/clean/bound outputs and dense/fallback assets. | [PR65](evidence/manual_provider_c3_v1/result.json): nine authored shells, not learned external-model execution; scoped C3 failed. | Approved runtime/weights/licences, provider fidelity and clean acceptance. |
| 6: Binding | [V1 binding](../src/closy_forge/manual_provider_c3_v1/binding.py) samples a lower-resolution lattice and serializes barycentric bindings. | [PR65](evidence/manual_provider_c3_v1/result.json): 99 rows (9 shells x 11 states), 16/17 gates; maximum rest error `0.0122075879 m` exceeds `0.008 m`, `MPC3-09`. | Geometry-based general binding, independent decoded-rest checking and accurate frames; parent owns successor repair. |
| 7: Material physics | [V2 evaluation path](../src/closy_forge/solver_material_v2/evaluation.py) executes material-coupled CPU solver inference and motion tests. | [PR64](evidence/solver_material_v2/canonical_result_envelope.json): 24 tuples, 576 garment motions; `SMV2-01` failed; mean normalized error `0.415668`. | Better parameter recovery and measured physical coupons; synthetic projection is not calibrated fabric dynamics. |
| 8: Families | [Family builders](../src/closy_forge/pipeline/build_long_sleeved_demo.py) exist for all nine declared families with distinct panels/semantics. | [PR66](evidence/static_zeroone_runtime_v2/result.json): six static successes; long-sleeved top, button shirt and jacket fail geometry. Full Phase 8 needs templates, semantics, capture tests **and simulation validation for each family**. | Parent's geometry/parameter matrix plus honest family-specific capture estimation and simulation evidence. Enum coverage or known-parameter round trips are insufficient. |
| 9: Learned patterns | [Training implementation](../src/closy_forge/pattern_inference/model_v2.py), grammar/decoders and structured corrections exist. | [Saved grouped coverage](blueprint_coverage.json) describes bounded E1/E2 execution; not a new evaluation or universal variable-topology recovery result. | Reliable compile/fit gates, unseen diverse data, correction UI and template-only comparisons. |
| 10: Static ZeroOne | [Static audit](../src/closy_forge/zeroone/static_stage_audit_v2.py) validates the optional read-only processor's derivatives. | [PR66](evidence/static_zeroone_runtime_v2/result.json): 6/9 static pass. Z4/Z5/Z6/Z8 each have 6 passes + 3 blocked; Z3/Z7 each have 6 `not_run` + 3 blocked. | Repaired input geometry, available read-only build, actual triangle/provenance coverage and bounds predicates. Equal triangle counts alone are not exact coverage. |
| 11: Dynamic ZeroOne | [Dynamic integration](../src/closy_forge/zeroone/dynamic_integration.py) and separate analytic mechanical-reference paths exist. | [Saved reconciliation](evidence/phase11_prerequisite_reconciliation_v2.json) blocks Phase 11 on refreshed paired scoped Z1 prerequisites. Analytic motion does not establish solver-driven dynamic readiness. | Admissible solver motion, dynamic derivatives, deformed bounds, cracks, LOD and measured performance. Gate **Z2** is not the dense-analysis stage **Z2** in section 9.5. |
| 12: Runtime/mobile | [V2 package loader](../src/closy_forge/runtime_delivery/package_v2.py) supports compressed packages, bounded decode, deterministic rebuilding, poses and resume. | [PR66](evidence/static_zeroone_runtime_v2/result.json): 24/36 valid rows, 12 invalid geometry, 8/9 recovery controls pass. Cross-package bytes were rejected for size rather than the expected hash reason. | Actual geometry validation and trusted metadata identity; isolate same-size cross-package vs wrong-size controls. Real device latency/memory/thermal/battery are `not_run`. |
| 13: Avatar/outfits | [Measurement fitter](../src/closy_forge/avatar_variation/fit_solver.py) and [radial layer solver](../src/closy_forge/layer_collision/solver.py) provide bounded synthetic geometric behavior. | [Synthetic avatar evidence](evidence/phase13_synthetic_avatar_fit_v1.json) does not grant licensed body/private-user/outfit acceptance. Radial matching is not arbitrary package-surface collision. | Actual meshes with mismatched tessellations, binding fidelity, outfit motion/quality and licensed body assets/consent. |
| 14: Native models | [Bounded model](../src/closy_forge/bounded_models/model.py) trains a material ranker and warning classifier. | [Saved model evidence](evidence/phase14_bounded_models_v1.json): source-only project-authored CPU fixture/advisory scope, globally partial. | Mature authorized data/evaluation, independent baselines, compute/licences; not a garment foundation model or calibrated fabric predictor. |

The machine-readable equivalent is `phase_overview()` in
[checkpoint.py](../src/closy_forge/blueprint_progress_v3/checkpoint.py). These saved outcomes are a
PR66 baseline; subsequent parent-owned results must identify their own profile, source and denominator.

## Parser And Mapping Contract

[parser.py](../src/closy_forge/blueprint_progress_v3/parser.py) is independent of
`capture_reconstruction_v2/blueprint_parser.py`; neither it nor the generator imports an evaluator.

- `sourceSection` is the nearest numbered document heading, such as `8.18` or `17`.
- `roadmapPhase` is an integer 0-14 from the nearest explicit `Phase N` heading, never an arbitrary
  section number. Invalid explicit phases are flagged for review, not silently assigned elsewhere.
- `roadmapPhases` can additionally cross-link an outside-roadmap requirement through an **explicit
  editorial section/gate map**. A multiply linked requirement is still one source requirement.
  Direct and cross-linked phase counts are separate; phase totals must not be added as a unique count.
- Unmapped architecture, quality, rights, risk and product requirements are `cross_cutting`, not
  invented phases. In particular section 12 is not Phase 12 and section 25 is not Phase 25.
- Noun lists inherit `Deliver`, `Required`, `Requirements`, acceptance headings and governing prose.
  Phase 8's trailing "Each family requires ..." governs its preceding family list. Nested list
  context is indentation-scoped. Explicit ownership ("It owns:") and conditional prerequisites
  ("Only after ...:") also govern lists. Prose/heading/fence boundaries reset local introductions.
- Headings, separators and fenced examples remain structural. Noun lists/tables without clear context
  are **ambiguous and retained**, not silently counted as non-requirements. This is a bounded Markdown
  parser, not an exhaustive natural-language requirements oracle; review is still necessary.
- Rows retain the raw block, heading path, line range, source-content identity, context block and
  classification reason. IDs include heading context and occurrence, allowing repeated requirement
  text without losing locations; blank-line insertion alone does not change IDs.

Explicit section cross-links, encoded in `SECTION_PHASE_LINKS` and `GATE_PHASE_LINKS`:

| Source | Roadmap link |
|---|---|
| 7; 8.1-8.3 | 2 |
| 8.4; 8.5 | 2/13; 2/3 respectively |
| 8.6; 8.7; 8.8 | 1/8; 0/1/8; 3/9 respectively |
| 8.9; 8.10; 8.11; 8.12 | 5; 1/8; 1/7/8/13; 3 respectively |
| 8.13; 8.14; 8.15-8.16; 8.17; 8.18; 8.19; 8.20 | 5; 5/6; 4; 7; 6; 13; 2/3/9/13 respectively |
| 9.1; 9.2-9.6; 9.7; 9.8-9.10; 9.11 | 10/11; 10; 10/11/12; 11; 0/10/11 respectively |
| 10; 13; 22; 23 | 0/12; 9/14; 0/1; 2/3 respectively |
| Gate C1; C2; C3; Z1; Z2 | 0/1; 5; 6; 10; 11 respectively |
| Gate P1 and all other unlisted sections | Cross-cutting |

Subsections inherit their nearest *explicitly mapped* section. These links express relevance, not
acceptance or dependency satisfaction, and can be reviewed in the new namespace without altering
historical inventories.

## Inventory Migration

The generator emits a full machine-readable crosswalk in `migration`, preserving **all 101 grouped
rows and all 239 V2 source rows**. Nothing updates their files in place.

| Inventory | Meaning at this baseline |
|---|---|
| [101 grouped rows](blueprint_coverage.json) | Historical editorial groups, including scoped "complete" statuses and stale statements. Fifteen explicit `BP-17-PHASE-NN` IDs map to current roadmap deliverables; the other 86 grouped rows remain visibly review-required, not guessed from ID digits or fuzzy summaries. |
| [239 V2 source rows](evidence/static_zeroone_runtime_v2/blueprint_inventory.json) | Frozen parser output: 60 partial, 164 not started, 9 not run, 6 dependency blocked. Its phase 1-25 summaries are section summaries. |
| V3 initial replay | 1,739 source blocks: 808 normative requirements, 482 ambiguous review blocks, 449 structural/descriptive blocks. These are extraction counts, **not completion scores**. |
| V2-to-V3 mapping | 231 historical source rows match current requirements by normalized text; eight requirement introducers are reclassified as governing context and flagged for review. 577 newly included source requirements are retained with classification reasons and anchors. `231 + 577 = 808`; every old row remains in the crosswalk. |

Concrete corrections include `simulation mesh;` under Phase 1 and `multiple garment collision layers;`
under Phase 13, both newly normative; Phase 8's eight family nouns are governed by its explicit
per-family requirement. An existing V2 row's historical `phase: "17"` stays visible in the crosswalk
beside its corrected roadmap assignment. Repeated text is not automatically a duplicate requirement.
The eight reclassified rows are the masks/labels and constraint-type introducers plus six Gate C/Z/P
introducers. Their current source block IDs and reasons remain in the migration, while their list
children retain those IDs as context anchors; they have not disappeared from the source record.

Historical statuses are retained verbatim, **not silently promoted or copied into broader rows**.
New requirement-level `status` / `implementationStatus` default to `unassessed`, while `evidenceStatus`
defaults to `not_reviewed`. This does not say implementation is absent: the inspected phase overview
above records implemented behavior separately. It also does not mean an old passing fixture regressed.

Explicit `assessments` can supply row-specific implementation/evidence anchors, scope, rationale and
dependencies. `not_started` requires an inspected absence; `complete` requires implemented code,
passing evidence and explicit scoped acceptance review. A file/schema/test's existence alone is not
completion. Unknown/stale assessment IDs and unsupported status values are rejected.
The generator does not supply automatic broad status overrides or an overall percentage.

## Read-Only Commands

From the integration worktree's Forge directory in PowerShell:

```powershell
Set-Location E:/apps/Closy-all-family-layer-integration-v1/closy-forge
$env:PYTHONPATH = 'src'
py -3.12 scripts/generate_blueprint_progress_v3.py --format summary
py -3.12 scripts/generate_blueprint_progress_v3.py --format markdown
py -3.12 scripts/generate_blueprint_progress_v3.py --format json
```

The wrapper reads saved files and writes **stdout only**. It invokes no Git/network operation,
geometry build, training, solver or protected evaluator. The JSON includes input hashes, an exact
normalized-source blob identity, every source block, the migration and the PR66 overview.
Markdown links are relative to the Forge root. Generated output is not automatically an authoritative
publication; a changed blueprint needs review even if the tool can parse it.

Focused checks only:

```powershell
py -3.12 -m pytest tests/unit/test_blueprint_progress_v3.py -p no:cacheprovider
py -3.12 -m ruff check src/closy_forge/blueprint_progress_v3 tests/unit/test_blueprint_progress_v3.py scripts/generate_blueprint_progress_v3.py
py -3.12 -m ruff format --check src/closy_forge/blueprint_progress_v3 tests/unit/test_blueprint_progress_v3.py scripts/generate_blueprint_progress_v3.py
py -3.12 -m mypy src/closy_forge/blueprint_progress_v3 tests/unit/test_blueprint_progress_v3.py scripts/generate_blueprint_progress_v3.py
```

## Handoff Boundary

Local focused receipt (2026-09-05): **56 tests passed in 1.58 s**; Ruff check passed and all six Python
files passed Ruff format checking. The summary, Markdown and full JSON generation paths executed;
the computed source blob matches the frozen 239-row inventory. No tracked existing-file diff was
present in the integration worktree at the preservation check. These are software/reporting receipts,
not new geometry, scientific or product quality outcomes.

Only the new V3 package, its pure unit test, this document and the new generator belong to this sidecar.
No existing import/default/caller is redirected, no golden snapshot is regenerated, and no active
resume file is modified. The parent should link this successor from its permitted current pointers
and update the overview after real Unit A/B/C evidence, without changing the PR63-66 recorded results.
Remaining extraction ambiguities and 101-row non-atomic mapping reviews are explicitly unresolved;
they do not justify replacing known implemented behavior with `not_started` or claiming full coverage.
