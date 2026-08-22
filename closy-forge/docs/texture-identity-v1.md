# Texture Identity v1

Implementation 04 adds `textures/texture_identity.json` as a deterministic material identity scaffold for the demo T-shirt package.

This contract does not claim real source-image texture reconstruction yet. The current fixture has no raster source photos, no UV projection pass, and no generated texture atlas. Instead, Forge records mobile-safe PBR observations derived from the authored render materials so downstream readers can distinguish deliberate material evidence from missing texture work.

## Artifact

`textures/texture_identity.json` contains:

- `sourceRecordId` and `sourceRecordHash` pointing to the immutable synthetic capture record.
- `sourceVisualUnderstandingId` and `sourceVisualRecordHash` pointing to analytic visual observations.
- `sourceFitReportId` and `sourceFitReportHash` pointing to the fitted T-shirt parameters.
- `sourceTextureAvailable`, `generatedAtlasAvailable`, and `textureProjectionRun`, all `false` for this milestone.
- `observedMaterialRegions`, one per render material used by the fixture.
- `projectionPlan`, describing the intended future target mesh, UV space, atlas size, seam blending policy, and occlusion policy.
- `pbrSafety`, documenting the mobile-safe material model and unsupported advanced shader features.
- `integrity.textureIdentityHash`, a canonical SHA-256 over the payload with the hash field blanked.

## PBR Evidence

Each observed material region currently stores authored fixture values:

- `baseColorFactor`: RGBA values in `[0, 1]`.
- `roughnessFactor`: clamped to at least `0.65`.
- `metallicFactor`: clamped to at most `0.1` for fabric.
- map availability flags for normal, roughness, metalness, and AO maps, all `false`.

These values are intentionally conservative for Expo/mobile rendering. They avoid transmission, dispersion, clearcoat, subsurface scattering, and other advanced material features that are not part of the current mobile-safe package contract.

## Validation

The package validator rejects texture identity reports when:

- source capture, visual observation, or fit hashes do not match;
- the canonical `textureIdentityHash` is stale;
- material regions reference unknown render material IDs;
- PBR factors are outside `[0, 1]` or non-finite;
- source texture state contradicts manifest capabilities;
- texture quality counts no longer match the texture identity payload.

## Future Production Path

The next texture milestones should replace authored fixture colours with real source evidence:

- source-image texture records with consent/privacy metadata;
- UV-space projection onto `render/fallback.glb` or a production mesh;
- atlas generation with seam blending and occlusion handling;
- optional normal/roughness/AO extraction;
- QA reports that compare generated maps against source views.
