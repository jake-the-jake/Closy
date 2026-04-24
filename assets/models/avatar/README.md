# Default Stylised Avatar Asset

Expected default body path:

- `assets/models/avatar/default-stylised-avatar.glb`

This file is the default attractive mannequin body for Closy Avatar Preview.
If it is missing or fails to load, the app falls back to the procedural mannequin.

Current placeholder:

- `default-stylised-avatar.glb` is a temporary seeded placeholder copied from the existing bundled body so the GLB pipeline is live immediately.
- Replace it with a proper stylised low-poly avatar when ready.

Expected rig / bone naming:

- `hips` or `root`
- `spine`
- `chest` or `spine2`
- `neck`
- `head`
- `upperArm_L` / `upperArm_R`
- `lowerArm_L` / `lowerArm_R`
- `hand_L` / `hand_R`
- `upperLeg_L` / `upperLeg_R`
- `lowerLeg_L` / `lowerLeg_R`
- `foot_L` / `foot_R`

Model expectations:

- Neutral relaxed bind pose
- Clean stylised mannequin silhouette
- Full body visible in a 1.75m to 1.8m normalized scale range after runtime normalization
- Simple clean materials that still look acceptable under fallback shading
- No baked debug helpers, grids, or garment shells in the body asset

R&D note:

This GLB pipeline is a temporary presentation layer for a better first impression.
Future production work should investigate:

- SMPL / SMPL-X style parametric body models
- MediaPipe/OpenPose-style body keypoints
- image-to-avatar reconstruction
- garment segmentation and learned garment deformation
- later native renderer or server-side avatar generation
