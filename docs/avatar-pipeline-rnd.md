# Closy Avatar Pipeline R&D

This document describes the practical direction for turning Avatar Preview into a stable product try-on feature without depending on runtime AI generation or brittle debug toggles.

## Current v1 Runtime

- User-facing route: `/avatar`
- Developer route: `/dev-avatar-preview`
- Runtime source priority: polished avatar GLB URL, bundled stylised GLB, procedural mannequin fallback
- Safe fallback: if a GLB loads but does not produce visible meshes, the viewport keeps the scene alive by switching to the procedural mannequin
- Normal user mode: clean avatar viewport, simple outfit/pose/style controls, no debug overlay
- Developer mode: diagnostics remain available behind the Debug tab or collapsible dev panel

## Asset Slots

Recommended bundled locations:

- `assets/models/avatar/default-avatar.glb`
- `assets/models/avatar/default-mannequin.glb`
- `assets/avatar/realistic/default-avatar.glb`
- `assets/avatar/stylised/default-mannequin.glb`

Metro cannot `require()` a missing GLB. Keep static imports pointed at known-present assets, and use documented slots for future drop-in assets.

## Model Format

Preferred format is GLB 2.0 with:

- Y-up orientation
- Feet resting on the ground plane
- Human height normalized around 1.75m
- One visible body mesh or a small number of named body meshes
- PBR materials with base color, roughness, metalness, and optional normal maps
- Texture sizes budgeted for mobile, ideally 1K or 2K max per material set

## Rig Expectations

Support common naming from:

- Ready Player Me / RPM-style GLB
- Mixamo-rigged GLB
- VRoid / VRM-derived rigs after conversion
- Blender armatures
- SMPL / SMPL-X-style exports after preprocessing

Required or preferred bones:

- hips/root
- spine
- chest
- neck
- head
- upperArm_L / upperArm_R
- lowerArm_L / lowerArm_R
- hand_L / hand_R
- upperLeg_L / upperLeg_R
- lowerLeg_L / lowerLeg_R
- foot_L / foot_R

Rendering must not depend on complete rig detection. If the rig is incomplete, show the neutral model and record the missing bones in diagnostics.

## Mobile Budget

Target budgets for v1/v2:

- Body mesh: 10k-35k triangles for normal mode
- Garments: 5k-20k triangles each, depending on garment category
- Textures: prefer compressed, power-of-two dimensions
- Materials: keep body and garment material counts low
- Skeleton: one armature for body; garments can initially use anchor-follow transforms before true skinning

## Garment Binding Strategy

V1 garments should bind to named anchors:

- shirt torso: chest, shoulderL, shoulderR, waist
- sleeves: shoulder to elbow/wrist
- trousers: waist, hip, knee, ankle
- shoes: foot anchors

Current procedural garments use weighted anchor follow. The next production step is to map the same anchor API to GLB bones or named empties, then move toward true skinned garment meshes.

## Why Cloth Simulation Is Later

Full cloth simulation is not a v1 requirement because it adds heavy runtime cost, collision complexity, and instability on mobile. Closy should first ship:

- stable avatar source selection
- reliable startup visibility
- believable garment seating
- pose-follow deformation
- good camera controls

Then iterate toward baked or learned cloth deformation for selected garment categories.

## Roadmap

V1:

- Stable `/avatar` user route
- Clean mannequin/fallback
- GLB source manager
- Anchor-based garment placement
- Debug-only canary diagnostics

V2:

- Higher-quality bundled stylised GLB
- Better rig retargeting
- Skinned garment test assets
- Outfit-aware garment selection

V3:

- External avatar generation/import pipeline
- SMPL/SMPL-X research path
- Learned or baked garment deformation
- Offline asset optimisation with Blender or gltf-transform
