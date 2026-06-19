# ZeroOne Avatar Asset Foundry

This document defines the future handoff between Closy and ZeroOne for production avatar assets.

## Ownership

Closy owns:

- User-facing avatar and outfit try-on experience.
- Wardrobe data, outfit composition, save/share/social flows.
- Body parameters, pose requests, camera requests, and mobile preview.
- Runtime fallback behavior when a candidate avatar package is missing or invalid.
- Lightweight garment proxy preview and developer diagnostics.

ZeroOne owns later:

- High-quality avatar generation or import.
- Mesh cleanup, retopology, and mobile LOD generation.
- Rig validation, skinning validation, and humanoid bone mapping.
- Texture baking and mobile material preparation.
- Collision proxy generation and garment anchor metadata.
- Garment simulation, fit validation, and high-quality offline preview renders.
- Optimized GLB export for Closy consumption.

No ZeroOne native runtime dependency is required in Closy for this pass.

## Package Contract

A future `ZeroOneAvatarAssetPackage` should contain:

- `packageManifest`: package id, schema version, authoring metadata, license, and budgets.
- `production GLB`: the primary humanoid skinned avatar.
- `LOD GLBs`: lower-cost variants for mobile quality tiers.
- `textureBundle`: albedo/baseColor, normal, roughness, metallic, AO, and optional skin approximation maps.
- `rigMapping`: resolved humanoid bone names and rig profile.
- `landmarks`: stable avatar-root-local fitting landmarks.
- `collisionProxies`: torso, pelvis, limbs, hands, feet, and head fit volumes.
- `garmentAnchorMetadata`: intended garment attachment points and follow weights.
- `validationReport`: mesh/material/texture/rig/mobile-budget audit output.
- `previewRenders`: optional PNG/WebP thumbnails for asset QA and UI style selection.

Closy should consume this package through the avatar manifest, loader audit, normalization, rig mapping, material normalization, and garment landmark layers. Closy should not need to know how ZeroOne authored the mesh.

## Current Bridge State

Closy currently treats `assets/models/avatar/default-stylised-avatar.glb` as a bridge asset for the Production Avatar source until `assets/models/avatar/production/production_avatar.glb` is installed and wired.

The canonical production slot is defined by:

- `assets/models/avatar/production/avatar.manifest.json`
- `assets/models/avatar/production/production_avatar.glb`

Run:

```bash
npm run closy:avatar-audit -- assets/models/avatar/default-stylised-avatar.glb
```

The audit result should be attached to any future ZeroOne package handoff before the runtime promotes it over the fallback mannequin.
