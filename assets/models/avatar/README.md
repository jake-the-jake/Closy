# Avatar Model Slots

Drop future bundled avatar GLBs here when replacing the temporary mannequin bridge:

- `production/production_avatar.glb` for a future polished or user-like avatar
- `stylised/stylised_avatar.glb` for a polished stylised mannequin
- `animations/idle.glb` or embedded idle animation
- `animations/walk.glb` or embedded walk animation
- optional `animations/pose_relaxed.glb`, `pose_tpose.glb`, `pose_apose.glb`

Expected export settings:

- GLB 2.0
- Y-up orientation
- Feet at ground plane
- Approximate human height normalized to 1.75m
- PBR materials with mobile-safe texture sizes
- Skeleton names close to Mixamo / Ready Player Me / Blender conventions

The app must continue to render the procedural fallback if these files are missing.
