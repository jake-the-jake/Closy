# Master Blueprint Progress Ledger

This ledger records executable evidence against `Closy_AI_3D_Garment_and_ZeroOne_Integration_Master_Blueprint.md`. It is not a roadmap substitute: entries marked complete require code, fixtures, reports, tests or explicit validation evidence.

## Dashboard

- Branch: `codex/closy-forge-phase-0`
- Head when last updated: `pending-current-increment`
- Current active increment: `BP-17-PHASE-01` deterministic T-shirt cloth assembly and settle
- Completed phases: `BP-17-PHASE-00`
- Partially complete phases: `BP-17-PHASE-01`
- Passed gates: `BP-18-GATE-C1`
- Blocked gates: `BP-18-GATE-Z1`, `BP-18-GATE-Z2`, `BP-18-GATE-P1`
- Next dependency-ready increment: `BP-17-PHASE-02` capture and visual-understanding slice
- Last focused verification: `python -m pytest` -> `42 passed`; `python -m closy_forge schemas check --schema-dir schemas/v1` -> fresh

## Core Principles And Architecture

| ID | Status | Scope | Dependencies | Implementation paths | Evidence | Commits | Known limitations | Next action |
|---|---|---|---|---|---|---|---|---|
| BP-05-01-PATTERN-FIRST | complete | Pattern/seam/simulation representation is canonical. | None | `closy-forge/src/closy_forge/garments/tshirt/`, `closy-forge/src/closy_forge/validation/` | Demo package includes `pattern/pattern.json`, seams, simulation topology and validator checks. | `30f7d08`, `3dd65b1` | Only T-shirt family. | Extend through capture fitting before new garment families. |
| BP-05-02-MULTI-REPRESENTATION | complete | Separate pattern, simulation mesh, render shell and binding. | Pattern-first contract | `pipeline/build_tshirt_demo.py`, `geometry/subdivision.py`, `binding/` | Summary reports 223 simulation vertices, 1308 render vertices and 1308 binding records. | `30f7d08` | Dense visual proposal and ZeroOne derivatives absent. | Add visual proposal provider only after Gate C2. |
| BP-05-03-SIM-DRIVES-RENDER | complete | Render shell follows simulation through stored binding. | Simulation/render topology | `binding/builder.py`, `binding/reconstruct.py` | Binding reconstruction max/RMS error `0.0`. | `30f7d08` | No pose-suite dynamic normals/tangents yet. | Gate C3 work after motion suite. |
| BP-05-04-PROVIDERS-NOT-ARCHITECTURE | complete | No raw provider output becomes canonical. | Domain boundary | `docs/future-handoff.md`, package capabilities | No AI/provider code in core; provider capabilities false. | `30f7d08`, `3dd65b1` | No provider adapter yet. | Add null/manual proposal stage in Phase 5. |
| BP-05-05-SPATIAL-CONFIDENCE | in_progress | Confidence is explicit and spatial where available. | Semantic graph | `semantic/confidence.json`, semantic graph confidence fields | Fixture confidence is machine-readable but not spatial maps. | `30f7d08` | No image evidence maps. | Phase 2 should add capture/mask confidence maps. |
| BP-05-06-HUMAN-CORRECTION | not_started | Structured corrections are product features. | Capture and inference records | None | None | None | No correction records/UI. | Add correction schema in Phase 2/3. |
| BP-05-07-DETERMINISTIC-STAGES | complete | Deterministic stage inputs, hashes, settings and reports. | Package writer | `provenance.json`, `reports/summary.json`, tests | Repeated builds byte-identical; fixed timestamp/seed. | `30f7d08`, `3dd65b1` | Wall-clock timing omitted from canonical package. | Keep volatile metrics outside canonical digest. |
| BP-05-08-ZEROONE-DOWNSTREAM | complete | ZeroOne optional, derived and capability-negotiated. | Package contract | `manifest.json`, docs | `zeroOne.required=false`, ZeroOne capabilities false. | `30f7d08` | No ZeroOne worktree integrated. | Evaluate Gate Z1 only when ZeroOne source exists. |
| BP-05-09-VISIBLE-EVIDENCE | not_started | Source evidence outranks priors. | Capture assets | None | None | None | No source images in fixture. | Phase 4 texture/source evidence. |
| BP-05-10-START-NARROW | complete | Start with fixed avatar and T-shirt. | None | `avatar/reference_avatar.py`, `garments/tshirt/` | Demo T-shirt package validates. | `30f7d08` | Only short-sleeved T-shirt. | Phase 8 expands families later. |
| BP-06-SYSTEM-ARCHITECTURE | in_progress | Headless foundry package boundary. | Forge project | `closy-forge/`, docs | CLI build/validate/report exist. | `30f7d08`, `3dd65b1` | No service API/orchestrator yet. | Add idempotent stage orchestration before provider work. |
| BP-07-CAPTURE-MODES | not_started | Capture modes A-E, metadata and quality. | Privacy/source records | None | None | None | No capture ingestion. | Begin Phase 2 with immutable synthetic capture fixtures. |

## Stage A Through U

| ID | Status | Scope | Dependencies | Implementation paths | Evidence | Commits | Known limitations | Next action |
|---|---|---|---|---|---|---|---|---|
| BP-08-A-INGESTION | not_started | Immutable source records, consent and deletion policy. | Privacy model | None | None | None | No source files accepted. | Add local synthetic capture manifest; no real user data. |
| BP-08-B-NORMALISATION-QC | not_started | Image orientation, crop and quality. | Ingestion | None | None | None | No images. | Add deterministic fixture quality scorer. |
| BP-08-C-SEGMENTATION | not_started | Garment/person masks and semantic visual parsing. | Capture records | None | None | None | No provider/model. | Add editable mask schema and null fixture masks. |
| BP-08-D-CAMERA-BODY | in_progress | Fixed avatar body/landmark contract. | Avatar fixture | `avatar/reference_avatar.py` | 19 landmarks and collision primitives validate. | `30f7d08` | No camera/body estimation from images. | Add `IBodyModel` abstraction only when capture begins. |
| BP-08-E-MULTIVIEW-FUSION | not_started | Multi-view registration and evidence fusion. | Capture/camera | None | None | None | No multi-view inputs. | Phase 2/3 after capture records. |
| BP-08-F-SEMANTIC-GRAPH | complete | T-shirt semantic graph, stable IDs and required seams/openings. | Pattern fixture | `garments/tshirt/semantic_graph.py` | Validator checks cross-references; corruption tests cover dangling refs. | `30f7d08`, `3dd65b1` | Only T-shirt ontology subset. | Add ontology entries per new family. |
| BP-08-G-PATTERN-REPRESENTATION | complete | Panels, curves, seams, openings and schema. | Semantic graph | `pattern_generator.py`, `schemas/v1/pattern.schema.json` | Curved panels and validation tests pass. | `30f7d08`, `3dd65b1` | No imported pattern migration. | Keep v1 explicit rejections. |
| BP-08-H-PATTERN-INFERENCE | in_progress | Level 1 parametric T-shirt template. | Pattern schema | `parameters.py`, `pattern_generator.py` | Bounded variants validate and stable seam IDs remain. | `30f7d08` | No image parameter prediction. | Phase 3 deterministic fitting from masks. |
| BP-08-I-GEOMETRY-PROVIDERS | not_started | Raw visual proposal provider interface/adapters. | Gate C2 prerequisites | None | None | None | No provider work; no API use. | Add null/manual provider after C2 contract. |
| BP-08-J-SIM-MESH-CONSTRUCTION | complete | Pattern-derived simulation mesh with panel UVs. | Pattern schema | `geometry/triangulation.py`, `assembly.py` | Mesh manifests retain `panelUvs`; corruption tests reject missing coordinates. | `30f7d08`, `3dd65b1` | Coarse fan triangulation. | Improve triangulation quality before richer cloth. |
| BP-08-K-CLOTH-SIMULATION | in_progress | CPU reference settle with gravity, seams, stretch, bend and body collision. | Simulation mesh and collision avatar | `simulation/reference_cloth_solver.py`, `simulation/*state.json`, `simulation/settle_diagnostics.json` | Solver unit test; package validates with `actualClothSettleAvailable=true`. | pending-current-increment | Self-collision unavailable; not production-grade cloth. | Add self-collision or richer body-collision tests later. |
| BP-08-L-FIT-REFINEMENT | not_started | Differentiable/iterative fit refinement. | Capture masks/depth and solver | None | None | None | No image evidence/losses. | Begin after Phase 3. |
| BP-08-M-MESH-ANALYSIS | in_progress | Mesh audit and repair report. | Mesh assets | `geometry/glb_io.py`, validator | GLB parse smoke and degenerate triangle corruption tests pass. | `30f7d08`, `3dd65b1` | No connected component/non-manifold analysis. | Add visual proposal mesh audit in Gate C2. |
| BP-08-N-GARMENT-RETOPOLOGY | in_progress | Simulation/render/runtime topology distinction. | Mesh construction | `subdivision.py`, binding docs | Separate render shell and simulation topology. | `30f7d08` | No learned/semantic retopology. | Improve fallback topology only after dense proposals. |
| BP-08-O-UV-STRATEGY | in_progress | Pattern-space UV retained. | Simulation mesh | mesh manifests, GLB `TEXCOORD_0` | Panel coordinates retained and validated. | `30f7d08`, `3dd65b1` | No atlas/source-view UVs. | Add texture projection UVs in Phase 4. |
| BP-08-P-TEXTURE-PBR | not_started | Source projection and PBR recovery. | Capture images and render shell | `render/materials.json` only | Authored flat PBR material exists. | `30f7d08` | No source texture, normal, AO or inpainting. | Phase 4. |
| BP-08-Q-MATERIAL-INFERENCE | in_progress | Conservative cotton jersey preset. | Material schema | `material_physics.json` | Solver consumes damping/thickness; material schema exported. | pending-current-increment | No learned preset selector/calibration. | Phase 7 preset library. |
| BP-08-R-SIM-TO-RENDER-BINDING | complete | CLSYBND1 barycentric binding and validation. | Simulation/render mesh | `binding/` | Reconstruction and topology mismatch tests pass. | `30f7d08`, `3dd65b1` | Normal/tangent dynamic strategy not implemented. | Gate C3 pose-suite work. |
| BP-08-S-LAYERING-ANIMATION | not_started | Layering, animation and fallback deformation. | Motion suite and multiple garments | None | None | None | Single garment only. | Phase 13. |
| BP-08-T-HUMAN-CORRECTION | not_started | Structured correction tools. | Capture/fitting schemas | None | None | None | No UI or correction records. | Phase 2/3. |
| BP-08-U-QUALITY-PROVENANCE | in_progress | Stage reports, provenance and quality gates. | All package stages | `reports/`, `provenance.json`, validator | Summary and validation reports generated; settle diagnostics added. | `30f7d08`, pending-current-increment | No capture/visual/runtime metrics yet. | Expand metrics with each stage. |

## ZeroOne Stages Z1 Through Z8

| ID | Status | Scope | Dependencies | Implementation paths | Evidence | Commits | Known limitations | Next action |
|---|---|---|---|---|---|---|---|---|
| BP-09-Z1-IMPORT-INVARIANTS | blocked_external | Headless ZeroOne import and invariants. | ZeroOne source/worktree | Closy-side package contract only | ZeroOne capabilities false and optional. | `30f7d08` | ZeroOne executable/source not present in this worktree. | Locate ZeroOne repo and inspect headless capability. |
| BP-09-Z2-DENSE-ANALYSIS | blocked_external | Dense analysis in ZeroOne. | Z1 | None | None | None | External ZeroOne dependency. | Complete Closy-side report protocol first. |
| BP-09-Z3-DETAIL-CLASSIFICATION | blocked_external | Geometry/bake/procedural detail classification. | Z2 and material/texture maps | None | None | None | No dense proposals or ZeroOne. | Phase 10 after Gate Z1. |
| BP-09-Z4-CLUSTER-CONSTRUCTION | blocked_external | Panel/material/deformation-aware clusters. | Z2 | None | None | None | ZeroOne unavailable. | Keep package semantic boundaries stable. |
| BP-09-Z5-HIERARCHICAL-LOD | blocked_external | Projected-error LOD hierarchy. | Z4 | None | None | None | ZeroOne unavailable. | Later ZeroOne integration. |
| BP-09-Z6-GEOMETRY-PAGES | blocked_external | Page/residency metadata. | Z5 | None | None | None | ZeroOne unavailable. | Later ZeroOne integration. |
| BP-09-Z7-BAKING-PROCEDURAL | blocked_external | GeomoTree garment detail nodes. | Z3/Z4 and textures | None | None | None | ZeroOne/GeomoTree unavailable. | Define request protocol before execution. |
| BP-09-Z8-RUNTIME-EXPORT | blocked_external | ZeroOne derivative export. | Z1-Z7 | None | None | None | ZeroOne unavailable. | Preserve conventional fallback. |
| BP-09-GEOMOTREE | blocked_external | Garment-specific GeomoTree nodes. | ZeroOne/GeomoTree source | None | None | None | External repo unavailable. | Add Closy-side seam/material metadata first. |
| BP-09-DYNAMIC-VG | blocked_external | Static/dynamic virtual geometry levels Z-A through Z-E. | Z1/Z2 and C3 | None | None | None | External ZeroOne dependency; no motion suite. | Re-evaluate after Gate C3. |

## Package, Software, Models, Data, Evaluation, Privacy And Compute

| ID | Status | Scope | Dependencies | Implementation paths | Evidence | Commits | Known limitations | Next action |
|---|---|---|---|---|---|---|---|---|
| BP-10-PACKAGE-CONCEPT | complete | Inspectable `.closygarment` directory with required canonical assets. | None | `package_io/`, docs | Package tree validates; generated outputs ignored. | `30f7d08`, `3dd65b1` | No zip/container. | Add migration only when transport needs demand. |
| BP-10-MANIFEST | complete | Manifest identity, inventory, hashes and capabilities. | Package writer | `pipeline/build_tshirt_demo.py`, schema | Hash/inventory corruption tests pass. | `30f7d08`, `3dd65b1` | Quality summary remains simple. | Expand per stage. |
| BP-10-COORDINATES | complete | Metres, RH, Y-up, +Z forward, CCW. | ADR | `contracts/common.py`, ADR | Validator rejects convention mismatch. | `30f7d08`, `3dd65b1` | Existing app GLB mismatch remains isolated. | Later app-runtime migration. |
| BP-10-STABLE-IDS-HASHES | complete | Stable IDs and topology/content hashes. | Mesh/pattern contracts | `package_io/hashing.py` | Golden digest and topology hashes stable. | `30f7d08` | No schema migration yet. | Add v2 only with migration/rejection. |
| BP-10-PROVENANCE | complete | Deterministic provenance graph. | Stage outputs | `provenance.json` | Records source kind, privacy flags, seed and stages. | `30f7d08`, pending-current-increment | No user source deletion graph yet. | Phase 2 source records. |
| BP-10-CAPABILITIES | complete | Truthful capability flags. | Package manifest | Manifest + validator | False ZeroOne claim rejected; settle capability validated. | `30f7d08`, pending-current-increment | Capabilities are fixture-level. | Add capability negotiation for service/runtime later. |
| BP-11-SERVICE-LAYER | in_progress | Python sidecar isolated from Expo/C++/ZeroOne. | Repo boundary | `closy-forge/` | Root docs and CI exist. | `30f7d08` | No HTTP/worker API. | CLI-first phases continue. |
| BP-11-PIPELINE-ORCHESTRATION | not_started | Idempotent stages, caching, resume/cancel/events. | Stage contracts | None | None | None | Current builder is a direct vertical slice. | Add local orchestrator before Phase 5/provider work. |
| BP-11-PROVIDER-ISOLATION | not_started | Separate worker environments for heavy providers. | Provider interfaces | None | None | None | Core env intentionally minimal. | Add profile manifests when providers begin. |
| BP-11-CLI | complete | Build, validate, report commands. | Package builder | `cli/main.py` | CLI integration tests pass. | `30f7d08` | No ingest/analyse/simulate commands yet. | Add commands per phase. |
| BP-11-API-SHAPE | not_started | Reconstruction job HTTP/service API. | Stable CLI/stages | None | None | None | No service. | After CLI contracts mature. |
| BP-11-STORAGE | not_started | Content-addressed/object storage model. | Source records | None | None | None | Local package only. | Phase 2 job records. |
| BP-11-OBSERVABILITY | in_progress | Timings, counts, diagnostics, validation outcomes. | Stage reports | Reports and settle diagnostics | Mesh counts, validation, settle diagnostics recorded. | pending-current-increment | No hardware/memory/provider cost metrics. | Add per-stage benchmark profile. |
| BP-12-MODEL-STRATEGY | not_started | Provider/model registry and baselines. | Data/eval contracts | None | None | None | No model/provider dependency. | Add registry before any model adapter. |
| BP-13-DATA-STRATEGY | not_started | Synthetic/real dataset manifests and splits. | Capture/pattern infrastructure | None | None | None | No datasets. | Start synthetic fixture manifests in Phase 2/9. |
| BP-14-EVALUATION | in_progress | Stage metrics and golden/regression suite. | Package stages | `tests/golden`, reports | Golden package summary and corruption suite pass. | `30f7d08`, pending-current-increment | No capture/appearance/runtime benchmarks. | Add metrics per stage. |
| BP-15-SECURITY-PRIVACY | in_progress | Privacy flags, no real user data, provider policy false. | Provenance | `provenance.json`, docs | `containsUserImagery=false`, external APIs false. | `30f7d08` | No real deletion flow or encryption. | Phase 2 source deletion graph before real captures. |
| BP-15-LICENSING | in_progress | Dependency and asset licence discipline. | Dependency choices | `THIRD_PARTY.md` | Direct/transitive dev deps recorded; no external models. | `30f7d08`, `3dd65b1` | No model/dataset registry. | Add before provider/data ingestion. |
| BP-16-COMPUTE-D0 | complete | CPU/schema/test profile. | Minimal dependencies | `pyproject.toml`, `requirements-dev.lock`, CI | Ruff/mypy/pytest/schema checks pass on CPU. | `30f7d08`, `3dd65b1` | No GPU checks. | Preserve as always-on gate. |
| BP-16-COMPUTE-D1 | blocked_external | Moderate local GPU profile. | GPU hardware/model env | None | None | None | No GPU env requested/available. | Add optional env after local providers. |
| BP-16-COMPUTE-D2 | blocked_external | 24GB+ NVIDIA/Linux worker profile. | Hardware/provider env | None | None | None | Not available in current worktree. | Later provider/simulation R&D. |
| BP-16-COMPUTE-D3 | blocked_external | Cloud research profile. | Cloud authority/credentials | None | None | None | No cloud credentials/approval. | Contract-only work first. |

## Phases 0 Through 14

| ID | Status | Scope | Dependencies | Implementation paths | Evidence | Commits | Known limitations | Next action |
|---|---|---|---|---|---|---|---|---|
| BP-17-PHASE-00 | complete | Contract and deterministic harness. | None | `closy-forge/` | Build/validate/report, schemas, tests, CI. | `30f7d08`, `3dd65b1` | One fixture only. | Keep D0 gate green. |
| BP-17-PHASE-01 | in_progress | Deterministic T-shirt construction and cloth settle. | Phase 0 | `garments/tshirt/`, `simulation/reference_cloth_solver.py` | T-shirt panels, constraints, material and reference settle run. | `30f7d08`, pending-current-increment | No self-collision/inspection render image. | Add richer simulation diagnostics or begin Phase 2. |
| BP-17-PHASE-02 | not_started | Capture and visual-understanding slice. | Phase 1 package baseline | None | None | None | No source images/masks. | Add immutable synthetic capture records and quality scoring. |
| BP-17-PHASE-03 | not_started | T-shirt pattern fitting from images. | Phase 2 masks/landmarks | None | None | None | No image evidence. | Deterministic optimisation after Phase 2. |
| BP-17-PHASE-04 | not_started | Texture identity recovery. | Capture/views/render shell | None | None | None | No source textures. | Add projection and confidence maps. |
| BP-17-PHASE-05 | not_started | Garment/avatar constrained visual provider integration. | Gate C2 | None | None | None | No provider registry. | Add null/manual provider first. |
| BP-17-PHASE-06 | in_progress | Robust sim-to-render binding. | Phase 1 topology | `binding/` | Static binding passes reconstruction/topology tests. | `30f7d08`, `3dd65b1` | No pose suite or normals/tangents. | Gate C3 next after motion. |
| BP-17-PHASE-07 | not_started | Material physics inference. | Material descriptor schema/data | None | None | None | Single authored preset only. | Add preset library and selector. |
| BP-17-PHASE-08 | not_started | Additional garment families. | Proven T-shirt + family templates | None | None | None | T-shirt only. | Sleeveless tops first. |
| BP-17-PHASE-09 | not_started | Learned structured pattern inference. | Data/eval infrastructure | None | None | None | No training data/models. | Build synthetic dataset first. |
| BP-17-PHASE-10 | blocked_external | ZeroOne offline/static integration. | ZeroOne repo and Gate Z1 | None | None | None | ZeroOne unavailable. | Locate/integrate headless ZeroOne. |
| BP-17-PHASE-11 | blocked_external | ZeroOne deformation integration. | Gate C3 and Z1 | None | None | None | No ZeroOne dynamic path. | After Phase 10 and C3. |
| BP-17-PHASE-12 | not_started | Runtime/mobile optimisation. | Valid packages and app integration plan | None | None | None | App untouched by Forge. | Later, isolate from dirty avatar files. |
| BP-17-PHASE-13 | not_started | Personalised avatars and outfit layering. | Privacy, body model rights, multiple garments | None | None | None | Fixed avatar only. | Synthetic avatars before real captures. |
| BP-17-PHASE-14 | not_started | Closy-native trained models. | Data/eval/model registry | None | None | None | No training. | Only after baselines and datasets. |

## Gates

| ID | Status | Scope | Dependencies | Implementation paths | Evidence | Commits | Known limitations | Next action |
|---|---|---|---|---|---|---|---|---|
| BP-18-GATE-C1 | complete | Canonical readiness for serious AI proposal work. | Phase 0 | Forge package/schema/validator | Deterministic T-shirt package validates. | `30f7d08`, `3dd65b1` | T-shirt/fixed avatar only. | Maintain before provider work. |
| BP-18-GATE-C2 | not_started | AI proposal readiness. | Raw/clean proposal contract | None | None | None | No proposal interface/report. | Add provider provenance/rejection path. |
| BP-18-GATE-C3 | in_progress | Dynamic binding readiness. | Stable topology and pose suite | `binding/` | Binding topology validation exists. | `30f7d08`, `3dd65b1` | No pose-suite normals/tangent strategy. | Add motion benchmark. |
| BP-18-GATE-Z1 | blocked_external | ZeroOne static readiness. | ZeroOne source/executable | None | None | None | External ZeroOne unavailable. | Locate repo and inspect. |
| BP-18-GATE-Z2 | blocked_external | ZeroOne dynamic readiness. | Z1 and C3 | None | None | None | External ZeroOne unavailable. | Later. |
| BP-18-GATE-P1 | blocked_external | Product/private beta readiness. | Privacy controls, app integration, monitoring | None | None | None | Needs product/legal/privacy authority and app work. | Complete source deletion and consent before real captures. |

## Risks, Success Definitions, Locked Decisions And Implementation Guidance

| ID | Status | Scope | Dependencies | Implementation paths | Evidence | Commits | Known limitations | Next action |
|---|---|---|---|---|---|---|---|---|
| BP-19-RISK-01-SINGLE-VIEW | in_progress | Mitigate single-view ambiguity. | Capture modes | Confidence docs | Hidden regions not inferred in fixture. | `30f7d08` | No capture. | Use multi-view/default uncertainty in Phase 2. |
| BP-19-RISK-02-BODY-GARMENT | in_progress | Avoid body/garment entanglement. | Fixed avatar | Avatar contract/collision | Fixed avatar first. | `30f7d08` | No personalised bodies. | Body abstraction later. |
| BP-19-RISK-03-AI-MESH | complete | AI mesh cannot become canonical. | Package boundary | Docs/capabilities | No provider output in canonical package. | `30f7d08` | No providers yet. | Keep raw proposal distinction. |
| BP-19-RISK-04-TEXTURE-HALLUCINATION | not_started | Preserve observed texture regions. | Capture/texture phase | None | None | None | No textures. | Phase 4. |
| BP-19-RISK-05-SCOPE-EXPLOSION | complete | Start narrow. | None | T-shirt-only validator | Unsupported class rejected. | `30f7d08` | One family only. | Add families one at a time. |
| BP-19-RISK-06-CLOTH-INSTABILITY | in_progress | Conservative solver diagnostics and rejection. | Solver | Validator/diagnostics | Non-convergence corruption rejected. | pending-current-increment | Self-collision absent. | Add motion/self-collision tests later. |
| BP-19-RISK-07-RETOPOLOGY-CORRESPONDENCE | in_progress | Preserve correspondence through binding/hash validation. | Binding | `binding/`, validator | Topology mismatches rejected. | `30f7d08`, `3dd65b1` | No external remeshing. | Dense proposal transfer maps later. |
| BP-19-RISK-08-ZEROONE-COUPLING | complete | Closy works without ZeroOne. | Package fallback | Manifest capabilities | ZeroOne optional false. | `30f7d08` | No ZeroOne derivative. | Later optional bridge. |
| BP-19-RISK-09-DYNAMIC-CLUSTERS | blocked_external | Dynamic cluster culling efficiency. | ZeroOne dynamic | None | None | None | External ZeroOne. | After Z2. |
| BP-19-RISK-10-DEPENDENCY-CONFLICT | in_progress | Keep core env minimal. | Dependency discipline | `requirements-dev.lock`, `THIRD_PARTY.md` | No ML/GPU deps in D0. | `3dd65b1` | No provider envs yet. | Isolate future workers. |
| BP-19-RISK-11-LICENSING | in_progress | Avoid restrictive deps/assets. | Dependency review | `THIRD_PARTY.md` | No external models/assets. | `30f7d08`, `3dd65b1` | No model registry. | Add before providers. |
| BP-19-RISK-12-PRIVACY | in_progress | No source/user data; provenance privacy flags. | None | `provenance.json` | Privacy flags false. | `30f7d08` | No deletion flow. | Phase 2 before real data. |
| BP-19-RISK-13-UNMEASURED-VISUAL | in_progress | Stage metrics, tests and reports. | Package reports | `reports/`, tests | Golden/settle diagnostics. | pending-current-increment | No visual screenshot metrics. | Add inspection previews later. |
| BP-19-RISK-14-MOBILE-TOO-EARLY | complete | Keep mobile app untouched until packages are valid. | Boundary | No `src/` staged | Existing dirty app files preserved. | `30f7d08` | No runtime consumption. | App integration only after package runtime contract. |
| BP-20-RESEARCH-PROTOTYPE | in_progress | Deterministic T-shirt pattern/simulation, future images/textures/binding. | Phases 0-6 | Forge package | Pattern, settle and binding exist. | pending-current-increment | No front/rear image fitting or textures. | Phase 2/3/4. |
| BP-20-ALPHA | not_started | Several categories, correction, providers, exports, ZeroOne static. | Many phases | None | None | None | Not alpha. | Complete phases 2-10. |
| BP-20-BETA | not_started | Personalisation, layers, privacy, dynamic ZeroOne. | P1/Z2 | None | None | None | Not beta. | Later. |
| BP-20-PRODUCTION | not_started | Reliable supported garment digitisation. | All gates | None | None | None | Not production. | Later. |
| BP-21-LOCKED-DECISIONS | complete | Preserve all 12 locked decisions unless evidence changes. | Blueprint | Docs/contracts | Domain-specific package, no raw AI canonical, ZeroOne optional. | `30f7d08`, `3dd65b1` | Needs ongoing review. | Recheck each increment. |
| BP-22-IMPLEMENTATION-01 | complete | Forge foundation and deterministic T-shirt vertical slice. | None | `closy-forge/` | 38 tests reported after hardening; current suite now 42 tests. | `30f7d08`, `3dd65b1` | Initial commit lacked settle. | Superseded by Phase 1 settle increment. |
| BP-23-IMPLEMENTATION-02 | in_progress | Deterministic stitch/body-collision/settle path. | Implementation 01 | `simulation/reference_cloth_solver.py` | Solver/diagnostics added; validation passes. | pending-current-increment | Self-collision/production solver absent. | Commit increment and begin Phase 2. |
