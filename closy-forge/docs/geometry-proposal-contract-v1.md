# Geometry Proposal Contract v1

Gate C2 introduces a safe boundary for visual geometry providers.

The current package uses `closy.manual_local_glb_import.v1` with a tiny project-authored GLB fixture to exercise local raw visual proposal import without calling external services or accepting provider geometry as canonical truth. The null provider remains available as a deterministic rejection adapter.

## Artifact

`proposals/raw_geometry_proposal.json` records:

- source capture, visual observation, fit and texture identity hashes;
- provider identity, version and policy metadata;
- avatar/garment-only request scope;
- raw proposal availability and clean proposal availability;
- package-relative raw proposal asset path when a local GLB is available;
- alignment rules for future imported geometry;
- geometry audit fields such as mesh count, visible mesh count, triangle estimate and bounds;
- quality state and rejection reasons;
- `integrity.geometryProposalHash`, a canonical SHA-256 over the payload with the hash field blanked.

`reports/geometry_proposal_quality.json` mirrors the raw proposal quality state for quick package inspection.

`reports/raw_geometry_topology.json` records deterministic topology diagnostics for the raw GLB: connected components, boundary edges, non-manifold edges, duplicate positions, degenerate triangles and per-mesh summaries. These diagnostics do not make the raw proposal canonical or clean.

`reports/geometry_cleanup_plan.json` records deterministic cleanup and repair recommendations derived from the raw topology diagnostics. It identifies required operations such as duplicate-position welding, boundary-loop classification, component stitching or semantic panel transfer, and later simulation binding generation. It is a planning artifact only: `cleanupRun`, `repairRun`, canonical acceptance and runtime acceptance remain false.

`reports/geometry_cleanup_result.json` and `proposals/manual_cleanup_preview.glb` record the first deterministic local cleanup adapter result. The adapter performs only safe operations that do not need garment semantic inference: duplicate-position welding and degenerate-triangle filtering. It preserves open garment surfaces and keeps repair, retopology, semantic transfer, simulation binding and canonical acceptance false.

`proposals/clean_geometry_proposal.json` records the D0 clean-proposal decision for the raw proposal. In the current fixture it is intentionally rejected because repair, semantic transfer and simulation binding have not run. It links to the raw topology diagnostics, cleanup plan and cleanup result so the rejection is based on inspected raw geometry and explicit missing repair work, not just provider metadata. `reports/clean_geometry_proposal_quality.json` mirrors that rejected state for quick inspection.

`proposals/provider_registry.json` records which provider boundary was selected for the package and which future providers remain unavailable or unconfigured.

## C2 Rules

Raw visual geometry proposals are never canonical garment truth. A provider output may help with visual reference, texture recovery or future dense detail, but panels, seams, simulation topology, avatar correspondence and package validation remain Closy-owned.

The validator rejects proposal records when:

- source hashes do not match the package artifacts;
- provider policy claims external API use, training use or user data in the null fixture;
- the request is not constrained to avatar/garment use;
- raw proposals do not explicitly forbid canonical use;
- the null provider claims raw or clean geometry availability;
- a manual local GLB proposal has stale asset hash, stale size, invalid path or mismatched audit;
- the raw topology report has stale source hashes, stale asset metadata or diagnostics that no longer match the GLB;
- the cleanup plan has stale source hashes, stale topology snapshots, mismatched recommended operations, executed-output claims or acceptance claims;
- the cleanup result has stale source hashes, stale output asset metadata, mismatched operation/topology evidence, policy violations or clean/canonical acceptance claims;
- the rejected proposal claims canonical acceptance;
- proposal quality reports no longer match the proposal payload.
- the clean proposal report claims availability, cleanup, repair, semantic transfer, simulation binding or canonical acceptance before those stages exist;
- the clean proposal report no longer references the raw proposal/provider registry/topology/cleanup-plan/cleanup-result hashes.

## Future Providers

Future adapters can include local research models, manual Blender imports, commercial APIs or other image-to-3D systems. Each adapter must preserve this boundary:

- provider output starts as raw proposal evidence;
- a geometry audit must run before any clean proposal is considered;
- topology diagnostics must run before cleanup/repair can be trusted;
- cleanup/repair recommendations must be deterministic and package-auditable before any cleanup adapter executes them;
- cleanup adapters may emit preview assets, but must record every operation and keep canonical acceptance blocked until semantic transfer and binding pass;
- a clean proposal must record cleanup, repair, semantic transfer and simulation binding results before canonical acceptance;
- rejected output remains reproducible and inspectable;
- no unsupported generic-object request is accepted by the Closy garment foundry;
- no external service is called without explicit consent and provider policy records.
