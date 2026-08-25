# Provider Registry Contract v2

Phase 5 begins by making provider selection explicit and package-auditable.

`proposals/provider_registry.json` records the geometry providers that the current package is allowed to consider. It is not a model output and it does not make any raw mesh canonical. The current registry uses `contractVersion=closy.provider_contract.garment_avatar_only.v1` and remains scoped to garments/avatars only.

## Current D0 Registry

The deterministic demo package currently declares:

- `closy.null_geometry_proposal_provider.v1`, a deterministic null/test adapter used to exercise rejection and provenance paths.
- `closy.manual_local_glb_import.v1`, the selected local-only manual GLB import adapter contract for the committed D0 fixture.
- `closy.local_open_model_geometry_adapter.v1`, a declared local open-model adapter boundary that remains `not_run_missing_runtime_or_weights` because ordinary CI may not install model extras, download weights, contact hubs, require GPU hardware or accept new terms.
- future external provider slots for Meshy, TRELLIS and Hunyuan3D marked unconfigured and disabled.

The committed fixture uses a tiny project-authored local GLB so the manual adapter path is exercised without external services. Its D0 package capability is therefore `manualGeometryImportAssetAvailable=true`, while `localOpenModelExecutionAvailable=false`, `externalGeometryProvidersConfigured=false`, and `cleanGeometryProposalAvailable=false`. `reports/raw_geometry_topology.json` inspects the raw GLB topology, `reports/geometry_cleanup_plan.json` recommends the required cleanup/repair work, `reports/geometry_cleanup_result.json` records preview-only local cleanup execution, and `proposals/clean_geometry_proposal.json` records that the raw GLB has not passed clean/canonical acceptance.

## Manual Import Contract

The manual adapter only accepts operator-supplied `.glb` candidates. It audits:

- GLB 2.0 parseability;
- positive mesh and primitive counts;
- positive triangle estimate;
- material count;
- byte size and content hash.

Accepted manual candidates are still raw visual proposals only. They must never become canonical pattern, seam, simulation or binding truth without a later successful repair, semantic transfer, simulation binding, clean proposal and validation stage. The current fixture records this as `quality.status=accepted_visual_reference` with `acceptedForCanonical=false`, followed by a topology report, a cleanup recommendation, a non-canonical cleanup preview, and a rejected clean proposal report.

## Provider Bake-Off Report

`reports/provider_bakeoff.json` compares the declared provider routes without granting canonical authority. The current report has `status=completed_d0_contract_only_clean_rejected`, `providerCount=3`, `executedProviderCount=1`, `notRunProviderCount=2`, `canonicalAcceptedProviderCount=0`, and selected best available provider `closy.manual_local_glb_import.v1` with `executionStatus=completed_manual_fixture_import`.

Each provider result records runtime profile, cost class, topology defect summary, silhouette/texture fidelity status, bindability status, license restriction status, network observation, cleanup effort and whether any raw proposal exists. The local open-model adapter is explicitly `not_run_missing_runtime_or_weights`; this is contract/serialization evidence only, not model execution evidence.

## Policy Rules

Provider records must remain constrained to avatars and garments:

- `supportedDomain=avatar_garment_only`;
- `allowsGenericObjects=false`;
- no runtime external APIs in D0;
- no training use;
- no user imagery or personal body data;
- external providers require future consent, terms review and isolated workers.

The validator rejects registry records that enable external processing, generic-object scope, duplicate provider IDs, stale hashes, missing contract blocks, unreviewed manual rights, local open-model execution claims without weights/runtime evidence, or mismatched quality summaries. It also rejects provider bake-off records that claim network access, canonical acceptance, unbounded cleanup effort, stale aggregates or local model execution. Raw-topology diagnostics, cleanup-plan records, cleanup-result records and clean-proposal records continue to fail closed if they drift from their source artifacts or claim clean/canonical acceptance before the required pipeline stages exist.
