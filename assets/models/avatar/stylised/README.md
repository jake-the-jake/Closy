# Stylised Avatar Slot

Place the polished stylised fallback avatar here:

- `stylised_avatar.glb`

This should be a friendly Closy mannequin or character-quality avatar, not primitive capsule/sphere/cylinder debug geometry.

Requirements:

- GLB 2.0, Y-up, feet on ground, facing forward.
- Humanoid skeleton if pose controls should drive it.
- PBR/mobile-safe materials.
- Target 20k-45k triangles, 1k textures preferred.
- Clean proportions suitable for outfit try-on and garment anchor extraction.

The current app still bridges to `assets/models/avatar/default-stylised-avatar.glb` until this canonical slot is populated and wired through Metro.
