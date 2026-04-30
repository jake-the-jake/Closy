# Closy Avatar Assets

This folder is the runtime asset convention for Avatar Preview and future production avatars.

Place body GLBs here when they are ready:

- `realistic/default-avatar.glb` for a generated or artist-authored high-quality human avatar.
- `stylised/default-mannequin.glb` for a friendly product mannequin fallback.
- `fallback/` is reserved for procedural configuration and notes, not a primary visual path.

Runtime expectations:

- Units: meters.
- Height: roughly 1.7-1.85 before normalization; the app normalizes to about 1.78.
- Orientation: Y-up, facing +Z, feet on ground if possible.
- Mesh names: descriptive names such as `Body`, `Head`, `Eyes`, `AvatarBody`.
- Material names: descriptive PBR materials such as `Skin`, `MannequinSkin`, `Eye`, `Hair`.
- Skeleton: one skinned hierarchy with common humanoid names.
- Mobile safety: one body mesh or a small set of meshes, reasonable texture sizes, no exotic shaders.

Preferred rig names:

- `hips` / `pelvis`
- `spine`
- `chest`
- `neck`
- `head`
- `upperArm_L`, `lowerArm_L`, `hand_L`
- `upperArm_R`, `lowerArm_R`, `hand_R`
- `upperLeg_L`, `lowerLeg_L`, `foot_L`
- `upperLeg_R`, `lowerLeg_R`, `foot_R`

The current code can also inspect Mixamo, Ready Player Me-ish, VRM-ish, SMPL-ish, Blender, and CesiumMan-style names.
