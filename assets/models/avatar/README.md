# Avatar Model Slots

Closy currently ships one working bundled GLB bridge at:

- `assets/models/avatar/default-stylised-avatar.glb`

That bridge asset is exposed to the app as the **Production Avatar** until a dedicated production file is added. The separate stylised and realistic slots are intentionally marked missing unless real assets exist.

## Expected Paths

- `production/production_avatar.glb`: the default product avatar path for Avatar Try-On and dev preview.
- `stylised/stylised_avatar.glb`: optional alternate stylised mannequin slot.
- `realistic/realistic_avatar.glb`: future scan, Ready Player Me, SMPL, VRM, or ZeroOne-generated high-quality avatar slot.
- `animations/idle.glb`, `animations/walk.glb`, or embedded animation clips for basic motion.
- `textures/`: shared texture references when a GLB uses external maps.

## GLB Requirements

- GLB 2.0.
- Y-up orientation.
- Feet at the ground plane.
- Approximate human height normalized to 1.75m to 1.8m.
- Meshes must be visible and renderable; a successful load without visible meshes is invalid.
- Keep skeleton naming close to Mixamo, Ready Player Me, VRM, Blender Rigify, or the custom Closy humanoid profile.
- Include enough humanoid bones for head, torso, arms, hands, legs, and feet if pose driving is expected.

## Material Requirements

Use mobile-safe PBR materials. Closy normalizes unsupported Expo GL material features at runtime, but source assets should prefer:

- Albedo/baseColor.
- Normal.
- Roughness.
- Metallic.
- Ambient occlusion.
- Optional emissive only when intentional.
- Optional skin/subsurface approximation baked into textures or simple material color.

Avoid relying on:

- Dispersion.
- Transmission.
- Clearcoat.
- Transparent body materials.
- Very large texture arrays or high draw-call material splits.

## Mobile Budgets

Target budgets for a product avatar:

- Triangles: 45k to 70k.
- Texture size: 1024 to 2048 per map.
- Draw calls: 8 to 12 for the body.
- Bones: 72 to 96.
- Materials: keep skin, hair, eyes, and clothing cleanly named.

## Blender Export Notes

- Apply transforms before export.
- Export as binary `.glb`.
- Include selected objects only.
- Include skinning and animations when available.
- Keep image textures embedded for simplest Expo bundling, or document external texture paths.
- Validate the exported GLB in a separate viewer before adding it to the app.

## Optimization Notes

`gltf-transform` or equivalent tooling can be used for:

- Pruning unused nodes/materials.
- Texture compression.
- Draco or meshopt compression if the runtime loader supports it.
- Deduplicating accessors and textures.
- Checking triangle, material, texture, and animation counts.

## Compatibility Notes

Future import paths may support Mixamo, Ready Player Me, VRM, SMPL-style sources, and ZeroOne-generated assets. The app cannot create a photorealistic production avatar from code alone; a real GLB/USDZ/source asset must be authored, generated, or imported into the appropriate slot.

The runtime keeps an emergency procedural fallback so the viewport never opens blank, but that fallback is not the desired product avatar path.
