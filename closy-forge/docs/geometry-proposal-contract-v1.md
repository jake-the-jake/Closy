# Geometry Proposal Contract v1

Gate C2 introduces a safe boundary for visual geometry providers.

The current implementation uses `closy.null_geometry_proposal_provider.v1`, a deterministic null adapter. It exists to exercise request, provenance, audit, quality and rejection paths without calling external services or pretending to have generated a useful mesh.

## Artifact

`proposals/raw_geometry_proposal.json` records:

- source capture, visual observation, fit and texture identity hashes;
- provider identity, version and policy metadata;
- avatar/garment-only request scope;
- raw proposal availability and clean proposal availability;
- alignment rules for future imported geometry;
- geometry audit fields such as mesh count, visible mesh count, triangle estimate and bounds;
- quality state and rejection reasons;
- `integrity.geometryProposalHash`, a canonical SHA-256 over the payload with the hash field blanked.

`reports/geometry_proposal_quality.json` mirrors the proposal quality state for quick package inspection.

## C2 Rules

Raw visual geometry proposals are never canonical garment truth. A provider output may help with visual reference, texture recovery or future dense detail, but panels, seams, simulation topology, avatar correspondence and package validation remain Closy-owned.

The validator rejects proposal records when:

- source hashes do not match the package artifacts;
- provider policy claims external API use, training use or user data in the null fixture;
- the request is not constrained to avatar/garment use;
- raw proposals do not explicitly forbid canonical use;
- the null provider claims raw or clean geometry availability;
- the rejected proposal claims canonical acceptance;
- proposal quality reports no longer match the proposal payload.

## Future Providers

Future adapters can include local research models, manual Blender imports, commercial APIs or other image-to-3D systems. Each adapter must preserve this boundary:

- provider output starts as raw proposal evidence;
- a geometry audit must run before any clean proposal is considered;
- rejected output remains reproducible and inspectable;
- no unsupported generic-object request is accepted by the Closy garment foundry;
- no external service is called without explicit consent and provider policy records.
