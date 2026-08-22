# Provider Registry Contract v1

Phase 5 begins by making provider selection explicit and package-auditable.

`proposals/provider_registry.json` records the geometry providers that the current package is allowed to consider. It is not a model output and it does not make any raw mesh canonical.

## Current D0 Registry

The deterministic demo package currently declares:

- `closy.null_geometry_proposal_provider.v1`, the selected test adapter used to exercise rejection and provenance paths.
- `closy.manual_local_glb_import.v1`, a local-only manual GLB import adapter contract.
- future external provider slots for Meshy, TRELLIS and Hunyuan3D marked unconfigured.

The committed fixture uses a tiny project-authored local GLB so the manual adapter path is exercised without external services. Its D0 package capability is therefore `manualGeometryImportAssetAvailable=true`, while `cleanGeometryProposalAvailable=false`. A separate `proposals/clean_geometry_proposal.json` rejection report records that the raw GLB has not passed cleanup, repair, semantic transfer or simulation binding.

## Manual Import Contract

The manual adapter only accepts operator-supplied `.glb` candidates. It audits:

- GLB 2.0 parseability;
- positive mesh and primitive counts;
- positive triangle estimate;
- material count;
- byte size and content hash.

Accepted manual candidates are still raw visual proposals only. They must never become canonical pattern, seam, simulation or binding truth without a later successful clean proposal and validation stage. The current fixture records this as `quality.status=accepted_visual_reference` with `acceptedForCanonical=false`, followed by a rejected clean proposal report.

## Policy Rules

Provider records must remain constrained to avatars and garments:

- `supportedDomain=avatar_garment_only`;
- `allowsGenericObjects=false`;
- no runtime external APIs in D0;
- no training use;
- no user imagery or personal body data;
- external providers require future consent, terms review and isolated workers.

The validator rejects registry records that enable external processing, generic-object scope, canonical manual assets, stale hashes or mismatched quality summaries. It also rejects clean-proposal records that claim the manual raw asset has become clean, bound or canonical before the required pipeline stages exist.
