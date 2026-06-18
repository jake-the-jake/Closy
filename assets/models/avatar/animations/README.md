# Avatar Animation Slots

Optional animation GLBs for future rigged avatars:

- `idle.glb`
- `walk.glb`
- `pose_relaxed.glb`
- `pose_tpose.glb`
- `pose_apose.glb`

Embedded animations in `production_avatar.glb` or `stylised_avatar.glb` are preferred for v1.

If no animation clip exists, Closy falls back to procedural bone rotations on mapped humanoid bones. If no skeleton exists, the asset renders in neutral pose and dev diagnostics report it as unrigged.
