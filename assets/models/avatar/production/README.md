# Production Avatar Slot

Place the production-quality biped avatar here when it is ready:

- `production_avatar.glb`
- `avatar.manifest.json`

Requirements:

- GLB 2.0, local/mobile-safe, no runtime network dependency.
- One continuous sculpted human body mesh where possible, or clean skinned mesh groups.
- Humanoid skeleton with hips, spine, chest, neck, head, arms, hands, legs, and feet.
- Embedded idle animation preferred; separate `animations/idle.glb` is also supported by the future pipeline.
- PBR materials with baseColor/albedo, normal, roughness, metallic, AO where useful.
- Runtime target: 20k-70k triangles, max 2k textures, sensible bone count, low draw calls.

Do not commit oversized source files here. Keep Blender/source assets outside the mobile bundle and export optimized GLB for the app.

Before wiring a candidate into the manifest as `available`, run:

```bash
npm run closy:avatar-audit -- assets/models/avatar/production/production_avatar.glb
```

The runtime will still validate mounted renderability before promoting the asset over the fallback mannequin.
