# Closy Neural Garment Foundry and ZeroOne Virtual-Geometry Integration

**Master R&D and implementation blueprint**  
**Version:** 1.0  
**Research snapshot:** 21 August 2026  
**Purpose:** Handoff document for a new work-mode conversation

---

## 1. How this document should be used

This document defines the complete technical direction for building Closy's garment-reconstruction system and later connecting it to the ZeroOne Nanite-style/GeomoTree system.

It is deliberately broader than a single coding prompt. It should be treated as:

- the architectural source of truth;
- a boundary between Closy-specific research and ZeroOne-specific rendering work;
- a staged roadmap rather than a request to implement everything in one pass;
- the context document that a new work-mode chat should inspect before producing the prompt for the first implementation.

The next work-mode chat should **not** immediately attempt to train a Meshy-scale foundation model or modify every Closy and ZeroOne subsystem. It should first inspect the relevant repositories, compare them with the contracts and phases in this document, and then produce a tightly bounded implementation prompt for the first milestone described in **Section 22**.

This document makes one central architectural decision:

> The canonical Closy garment is a structured, simulation-ready garment consisting of sewing panels, seams, semantic parts, material properties and body correspondence. Generic AI-generated geometry is an input proposal and visual-detail source, not the canonical truth. ZeroOne is an optional downstream high-detail geometry processor and renderer, not the garment simulator or garment-understanding system.

That decision is the main protection against building an impressive image-to-3D demo that cannot later fit, animate, resize, layer or simulate clothing correctly.

---

## 2. Executive decision

Closy should be developed as two cooperating but independently testable halves.

### Half One — Closy Neural Garment Foundry

This half receives one or more user images and constructs a reusable garment asset. It owns:

- capture and image-quality assessment;
- garment/person segmentation;
- camera, pose and body estimation;
- garment classification and semantic decomposition;
- sewing-pattern inference;
- seam and panel topology;
- cloth simulation topology;
- fitting to a canonical or personalised avatar;
- physical material estimates;
- source-faithful texture reconstruction;
- high-resolution visual-geometry proposals;
- simulation-to-render-mesh binding;
- quality scoring, provenance and human correction;
- export of a versioned Closy garment package.

### Half Two — ZeroOne virtual-geometry backend

This half consumes the validated visual representation from Half One. It owns:

- dense-mesh inspection and repair where appropriate;
- hierarchical cluster construction;
- screen-space geometric LOD;
- geometry-page creation and residency metadata;
- visibility and occlusion structures;
- high-detail baking and procedural detail generation;
- GeomoTree-authored stitching, folds, weave and surface detail;
- high-quality desktop preview derivatives;
- later, cloth-driven deformation of clustered high-detail geometry;
- mobile/runtime derivatives and fallback outputs.

### The development decision

Do **not** wait for ZeroOne to be fully complete before starting Half One. Most of the difficult Closy work occurs before virtualised geometry is relevant. At the same time, do **not** recreate ZeroOne's generic geometry pipeline inside Closy.

The two halves should meet at a versioned package and command-line/API boundary:

```text
Closy garment reconstruction
        |
        | produces a validated .closygarment package
        v
ZeroOne asset foundry
        |
        | produces optional virtual-geometry derivatives
        v
Closy runtime / desktop preview / mobile fallback
```

ZeroOne must remain optional during early development. Every garment package must retain a conventional GLB or equivalent fallback so that Closy can continue functioning when ZeroOne processing is unavailable or incomplete.

---

## 3. Product mission

The long-term product goal is:

> A user supplies photographs or a short guided capture of a real garment. Closy reconstructs an editable, simulation-ready digital garment, fits it to the user's avatar, preserves the garment's visible design and material character, predicts plausible hidden structure, and displays it at a quality appropriate to the device.

This is not merely “turn an image into a mesh.” A successful garment must support:

1. **Identity** — it should still look like the uploaded garment.
2. **Structure** — sleeves, collar, waist, panels, openings and seams should be represented meaningfully.
3. **Fit** — it should align to a body of known shape and measurements.
4. **Simulation** — it should drape and move rather than behave like a rigid statue.
5. **Editability** — dimensions, fit, material and appearance should be adjustable.
6. **Layering** — it should eventually coexist with underwear, shirts, jackets and accessories.
7. **Animation** — it should follow a posed or animated avatar.
8. **Scalability** — it should have desktop, mobile and high-detail render derivatives.
9. **Traceability** — the system should know which regions are observed, inferred or generated.
10. **Safety and privacy** — user photographs and body estimates must be handled as sensitive personal data.

A generated object that resembles a shirt in one turntable render but has fused sleeves, no neck opening, unusable UVs and no body correspondence does not satisfy this mission.

---

## 4. What must not be conflated

Several adjacent technical problems look similar in a screenshot but require different representations and algorithms.

### 4.1 Generic 3D generation is not garment reconstruction

A generic image-to-3D model tries to produce a visually plausible surface. Garment reconstruction must infer hidden panels, openings, seams, body clearance and physical behaviour.

### 4.2 Retopology is not semantic garment topology

A clean triangle or quad mesh can still be structurally wrong. Closy needs to know that an edge is a cuff, an armhole, a waistband or one side of a stitched seam.

### 4.3 UV unwrapping is not sewing-pattern recovery

A generic UV atlas cuts a surface into charts for texturing. A sewing pattern represents how fabric was cut and stitched. The two can overlap, but they are not interchangeable.

### 4.4 Rigging is not cloth simulation

Skinning a shirt to the body skeleton can provide a cheap fallback preview, but it will not produce realistic drape, lag, folding or collision behaviour.

### 4.5 Nanite-style rendering is not simulation

Clustered virtual geometry determines what detail should be rendered and streamed. It does not decide how fabric stretches, bends, collides or settles.

### 4.6 Appearance accuracy is not physical accuracy

A generated normal map may imitate folds without giving the garment correct mass, bending stiffness, stretch or friction.

### 4.7 A high-resolution mesh is not automatically a high-quality asset

Millions of triangles can encode noise, self-intersections and hallucinated details. Quality must be measured by structure, fidelity, deformation and runtime behaviour, not triangle count alone.

---

## 5. Core design principles

These principles should survive individual model and library changes.

### 5.1 Pattern-first canonical truth

The canonical garment should contain an explicit pattern and seam graph whenever the category supports cut-and-sew construction.

### 5.2 Multiple representations, one garment

Closy should not force one mesh to perform every job. A garment may have:

- a 2D pattern representation;
- a low/medium-resolution simulation mesh;
- a dense visual render mesh;
- a skinned emergency/fallback mesh;
- ZeroOne cluster and page data;
- mobile baked derivatives.

### 5.3 The simulation mesh drives the render mesh

Cloth physics should run on a regular, semantically useful simulation mesh. The dense mesh follows it through a stored binding.

### 5.4 Existing models are providers, not the architecture

Meshy, Hunyuan3D, TRELLIS and future models should sit behind adapters. Replacing a provider must not rewrite the garment package, simulation or app.

### 5.5 Confidence must be spatial and explicit

Every reconstructed region should be marked as observed, triangulated from several views, inferred from symmetry, generated by a prior or manually corrected.

### 5.6 Human correction is a product feature, not a failure

Ambiguous images cannot always determine hidden construction. The system should provide concise correction tools instead of silently inventing certainty.

### 5.7 Deterministic stages and reproducible assets

Every pipeline stage should record its input hashes, model versions, parameters, random seed, output hashes, warnings and timings.

### 5.8 ZeroOne is downstream and capability-negotiated

A valid Closy garment must exist before ZeroOne processing. ZeroOne may add premium derivatives but must not silently change canonical seams or simulation topology.

### 5.9 Visible evidence outranks generative priors

Logos, text, patterns, trim and silhouette visible in source photographs should be preserved by projection or reconstruction. Generative inpainting should mainly fill genuinely unseen regions.

### 5.10 Start narrow and expand by garment family

The initial vertical slice should be a basic short-sleeved T-shirt on one fixed avatar. Arbitrary garments should emerge from proven category families, not from a premature universal model.

---

## 6. System-level architecture

```text
USER CAPTURE
  front / rear / side / details / optional video / measurements
                              |
                              v
CAPTURE INGESTION AND QUALITY GATE
  orientation, blur, exposure, view labels, privacy, metadata
                              |
                              v
VISUAL UNDERSTANDING
  masks, human pose, body estimate, camera, depth, garment parts
                              |
                              v
GARMENT SEMANTIC GRAPH
  category, panels, openings, seams, trims, layers, landmarks
                              |
              +---------------+----------------+
              |                                |
              v                                v
PATTERN HYPOTHESES                    VISUAL-GEOMETRY PROPOSALS
  template/retrieval/generated        Hunyuan/TRELLIS/Meshy/manual
              |                                |
              +---------------+----------------+
                              v
SIMULATION-READY CONSTRUCTION
  panel triangulation, stitches, cloth parameters, collisions
                              |
                              v
DIFFERENTIABLE / ITERATIVE FITTING
  compare rendered drape to masks, landmarks, depth and views
                              |
                              v
TEXTURE AND MATERIAL RECOVERY
  source projection, seam blending, PBR and physical descriptors
                              |
                              v
SIMULATION-TO-RENDER BINDING
  barycentric/cage mapping, offsets, confidence, accessories
                              |
                              v
CLOSY GARMENT VALIDATION
  pattern, mesh, physics, fidelity, runtime and provenance gates
                              |
                              v
VERSIONED .closygarment PACKAGE
                              |
              +---------------+----------------+
              |                                |
              v                                v
STANDARD GLB FALLBACK                    ZEROONE ASSET FOUNDRY
                                           clusters / pages / LOD
                                           GeomoTree detail / baking
                                                   |
                                                   v
                                         PREMIUM RUNTIME DERIVATIVES
```

The first half should be deployable as a headless service and CLI. The mobile app should submit capture data, receive job progress and display resulting assets; it should not run large 3D foundation models locally in the first versions.

---

## 7. Input modes and capture strategy

The pipeline should support several input modes, but they should be introduced in increasing order of difficulty.

### 7.1 Mode A — Flat or hung garment capture

The garment is photographed without a person, ideally against a plain background.

Advantages:

- no body occlusion;
- easier silhouette extraction;
- easier front/rear texture capture;
- clearer garment proportions.

Limitations:

- little evidence of drape on a body;
- sleeves and folds may collapse;
- scale still requires a reference or measurements.

### 7.2 Mode B — Garment worn by a person

This is the most natural consumer input and the most ambiguous.

The pipeline must separate:

- body shape;
- body pose;
- garment shape;
- image perspective;
- material behaviour;
- occluded or compressed regions.

### 7.3 Mode C — Guided multi-image capture

Recommended production capture:

- front;
- rear;
- left or right side;
- optional three-quarter view;
- optional close-ups of labels, texture, closures and patterning.

The app should guide distance, framing, turn angle and lighting. It should reject or warn about severe blur, clipped regions, mirrors, hands covering seams or inconsistent garments across views.

### 7.4 Mode D — Short guided video

A slow turn or orbit can provide many views and temporal mask consistency. Frames should be selected for sharpness and viewpoint coverage rather than processing the entire video indiscriminately.

### 7.5 Mode E — Single-image fallback

Single-image reconstruction should remain available, but output confidence must be lower. Hidden surfaces, rear construction and fabric behaviour are underdetermined.

### 7.6 Capture metadata

Useful optional metadata includes:

- garment category;
- labelled size;
- brand size chart;
- known fabric composition;
- stretch description;
- garment measurements;
- wearer height and body measurements;
- whether the image depicts a flat garment or a worn garment;
- which image is front/rear/side;
- whether colour fidelity is important;
- whether a known-size reference object or calibration marker is present.

The system should work without all metadata but should use it to reduce uncertainty.

### 7.7 Capture-quality score

Each capture set should receive a machine-readable score covering:

- foreground coverage;
- focus/blur;
- exposure and clipping;
- background separation;
- view diversity;
- garment consistency across images;
- occlusion;
- scale observability;
- colour reliability;
- visible semantic landmarks.

Low-quality captures should be rejected before expensive model inference where possible.

---

## 8. Half One: Closy Neural Garment Foundry

### 8.1 Stage A — Ingestion, privacy and immutable source records

Every reconstruction begins as a job with immutable source records.

A job record should include:

```json
{
  "jobId": "uuid",
  "schemaVersion": 1,
  "createdAt": "ISO-8601",
  "inputMode": "guided_multi_image",
  "images": [
    {
      "assetId": "uuid",
      "sha256": "...",
      "declaredView": "front",
      "orientationApplied": 90,
      "consentScope": "reconstruction_only"
    }
  ],
  "garmentHints": {
    "category": "tshirt",
    "sizeLabel": "M",
    "fabricComposition": "95% cotton, 5% elastane"
  },
  "bodyHints": {
    "heightMeters": 1.72,
    "avatarId": "closy-avatar-v1"
  },
  "providerPolicy": {
    "allowExternalApis": false,
    "allowTrainingUse": false
  }
}
```

Requirements:

- original files are never overwritten;
- derived images have their own hashes and provenance;
- EXIF is normalised and sensitive metadata is stripped from exported assets;
- retention and deletion policies are explicit;
- external-provider use is recorded and requires the applicable consent;
- failed jobs remain reproducible from stored stage manifests while source data exists.

### 8.2 Stage B — Image normalisation and quality control

Operations may include:

- orientation correction;
- lens-distortion correction when camera metadata is known;
- exposure normalisation;
- background masking;
- white-balance estimation;
- optional colour-card calibration;
- foreground crop with padding;
- super-resolution only when it does not invent identity-critical detail;
- removal of cast shadows from texture inputs while preserving shape cues in separate channels;
- duplicate-frame elimination for video input.

The pipeline should preserve both a visually normalised image and an evidence image. Aggressive cleanup should not destroy logos, stitching, fabric grain or shadows needed for geometry inference.

### 8.3 Stage C — Segmentation and semantic visual parsing

The visual-understanding subsystem should be provider-based. It may use a promptable segmentation foundation model, a fashion-specific segmentation network, or both.

Required masks and labels include:

- person/background;
- target garment versus other garments;
- exposed body regions;
- hair and hands that occlude the garment;
- garment semantic parts such as torso, sleeves, collar, cuffs, waistband, pockets, hood, lapels or legs;
- visible openings and boundaries;
- printed graphics, logos, buttons, zips and other details;
- uncertainty and occlusion masks.

For video or multi-view input, identities should be tracked across frames. A sleeve in one frame should retain the same semantic identity in another.

The output must be editable. A small amount of user correction to a mask can be more valuable than a long downstream optimisation against the wrong silhouette.

### 8.4 Stage D — Camera, depth, pose and body estimation

The system needs a consistent explanation of the camera and body before it can infer garment shape.

Estimate:

- camera intrinsics or an approximate field of view;
- camera extrinsics for each view;
- body pose;
- body shape parameters or a fit to the selected avatar;
- monocular depth cues;
- ground plane and scale where observable;
- image-space body and garment landmarks.

A parametric body model such as SMPL-family technology may be useful for research, but Closy must hide it behind an `IBodyModel` abstraction. Commercial rights, generated-output rights and model/software licences must be reviewed independently. The system must not bake a restrictive research-only dependency into its core data contract.

Initial development should use one fixed, clean Closy avatar with:

- known unit scale;
- known neutral pose;
- stable skeleton names;
- consistent body-region labels;
- collision surface or signed-distance representation;
- body measurements;
- stable topology hash.

Personalised body recovery should be added after the basic garment pipeline works.

### 8.5 Stage E — Multi-view registration and evidence fusion

For multiple images, the pipeline should determine which observations refer to the same surface regions.

Outputs include:

- calibrated or approximate camera matrices;
- per-view segmentation and depth;
- correspondences between garment landmarks;
- view reliability weights;
- visibility maps;
- a fused visual-evidence volume or feature representation;
- a spatial confidence map.

Multi-view diffusion may generate missing views, but generated views must be labelled as synthetic evidence. They should support hidden-surface hypothesis generation, not overrule real photographs.

### 8.6 Stage F — Garment ontology and semantic graph

A garment should be described before it is meshed.

The ontology should gradually cover:

- upper-body garments;
- lower-body garments;
- dresses and one-piece garments;
- outerwear;
- underwear/base layers;
- soft accessories;
- rigid accessories and trims.

The semantic graph should contain nodes such as:

```text
Garment
  Category: TShirt
  LayerClass: MidLayer
  Components:
    FrontTorsoPanel
    BackTorsoPanel
    LeftSleevePanel
    RightSleevePanel
    NeckBand
  Openings:
    Neck
    LeftSleeveCuff
    RightSleeveCuff
    Hem
  Seams:
    LeftShoulder
    RightShoulder
    LeftSide
    RightSide
    LeftArmhole
    RightArmhole
    NeckBandJoin
  Details:
    PrintedGraphic
```

Each semantic entity should have a stable ID that survives remeshing. Raw vertex indices are not stable semantic identifiers.

The graph should also encode:

- symmetry relationships;
- part hierarchy;
- expected seam pairings;
- garment layer and collision order;
- optional closures;
- optional rigid or semi-rigid details;
- confidence and evidence sources.

### 8.7 Stage G — Canonical pattern representation

Closy should define its own versioned pattern schema, informed by systems such as GarmentCode and recent structured garment representations, but not permanently tied to one research project's implementation.

A panel should contain:

- stable panel ID;
- semantic role;
- 2D local coordinate system in metres;
- ordered boundary curves;
- notches and landmarks;
- grain direction;
- fold lines;
- symmetry links;
- material region;
- optional seam allowance;
- triangulation constraints;
- confidence and provenance.

Boundary curves should support at least:

- line segments;
- circular arcs;
- quadratic Béziers;
- cubic Béziers;
- sampled splines for imported results.

A seam should contain:

- stable seam ID;
- two or more boundary spans;
- orientation of each span;
- stitch type;
- easing/gather ratio;
- attachment order;
- confidence;
- whether it is inferred, observed or user-corrected.

Example conceptual schema:

```json
{
  "patternVersion": 1,
  "panels": [
    {
      "id": "panel.front",
      "semanticRole": "front_torso",
      "grainDirection": [0.0, 1.0],
      "boundary": [
        {"id": "edge.hem.front", "type": "line", "points": [[-0.28, 0.0], [0.28, 0.0]]},
        {"id": "edge.side.right", "type": "cubic", "points": [[0.28, 0.0], [0.29, 0.25], [0.25, 0.52], [0.22, 0.62]]}
      ]
    }
  ],
  "seams": [
    {
      "id": "seam.left_side",
      "a": {"panel": "panel.front", "edge": "edge.side.left"},
      "b": {"panel": "panel.back", "edge": "edge.side.left"},
      "orientation": "opposed"
    }
  ]
}
```

### 8.8 Stage H — Pattern inference strategy

Pattern inference should evolve through four levels.

#### Level 1: Parametric category templates

Start with known panel structures for a T-shirt, vest, simple skirt, basic trousers and similar categories. AI predicts measurements and shape parameters, not arbitrary topology.

This provides:

- reliable seams;
- predictable simulation;
- interpretable controls;
- straightforward data generation;
- a tractable first product.

#### Level 2: Template retrieval and adaptation

Retrieve the closest pattern family from a library, then optimise its dimensions and curve controls against the capture.

#### Level 3: Structured program generation

A multimodal model generates a constrained pattern program or structured graph. The result must pass grammar, geometry and simulation validators before use.

#### Level 4: Template-free structured pattern generation

Later models may generate a variable number of panels and arbitrary seam graphs, similar in spirit to recent PatternGSL-style work. Even then, generation should occur inside a strict language with validation, not as unrestricted JSON or free-form polygons.

The inference system should be able to produce several hypotheses. A ranker can evaluate:

- silhouette agreement;
- seam plausibility;
- panel simplicity;
- category prior;
- physical stability;
- collision behaviour;
- consistency across views;
- user-provided measurements.

The top result and close alternatives should be retained until the quality gate is passed.

### 8.9 Stage I — Geometry-proposal providers

Generic image-to-3D systems should be connected through a provider interface.

```python
class GeometryProposalProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    def capabilities(self) -> ProviderCapabilities: ...

    def generate(self, request: GeometryProposalRequest) -> GeometryProposalResult: ...
```

A request may contain:

- foreground images;
- masks;
- view labels and cameras;
- category prompt;
- desired topology style;
- target resolution;
- texture/PBR request;
- deterministic seed where supported;
- privacy/provider policy.

Possible adapters include:

- a local Hunyuan3D adapter;
- a local TRELLIS.2 adapter;
- a Meshy API adapter;
- future local or commercial systems;
- a manual-import adapter for Blender-authored assets;
- a null/deterministic test adapter.

The proposal result should include:

- raw mesh or representation;
- materials and textures;
- provider/version/seed;
- camera assumptions;
- processing warnings;
- model terms and provenance metadata;
- a quality report;
- no claim that its topology is simulation-ready.

For Closy, these providers are useful for:

- a high-resolution visual shell;
- hidden-surface proposals;
- decorative geometry;
- folds and silhouette suggestions;
- initial PBR material maps;
- comparison baselines.

They should **not** define canonical seams, panel IDs, cloth constraints or body correspondence.

### 8.10 Stage J — Simulation-mesh construction

The simulation mesh should be generated primarily from the 2D panels, not obtained by generic retopology of the visual mesh.

Requirements:

- controlled edge length;
- reasonably regular triangles;
- exact preservation of semantic panel boundaries;
- compatible vertex counts or resampling along sewn edges;
- stable panel-local UV coordinates;
- no zero-area or inverted elements;
- material-region support;
- optional adaptive density near collars, cuffs, folds or closures;
- deterministic triangulation for a given pattern and settings.

Because every simulation vertex originates in 2D pattern space, the first UV set can be the panel coordinate itself. This removes much of the generic UV-unwrapping problem for the simulation representation.

The simulation mesh should retain:

- panel ID per face;
- 2D rest coordinates per vertex;
- seam constraints;
- grain direction;
- material region;
- body-region correspondence where known;
- topology hash.

### 8.11 Stage K — Cloth simulation backend

Closy needs a backend abstraction rather than a solver hard-coded into every stage.

```python
class ClothSimulationBackend(Protocol):
    def prepare(self, garment: SimulationGarment, avatar: CollisionAvatar) -> PreparedSimulation: ...
    def settle(self, prepared: PreparedSimulation, settings: SettleSettings) -> SimulationState: ...
    def simulate(self, prepared: PreparedSimulation, motion: AvatarMotion) -> SimulationSequence: ...
```

The initial solver should favour robustness and inspectability. An XPBD-style solver is a sensible starting point for panel sewing and drape.

Required constraint types eventually include:

- edge/stretch constraints;
- anisotropic warp and weft stretch;
- shear constraints;
- bending constraints;
- seam/stitch constraints;
- attachment and pin constraints;
- body collision;
- self-collision;
- garment-to-garment collision;
- thickness and separation;
- friction;
- damping;
- optional pressure for inflated garments;
- rigid/semi-rigid attachments for buttons and hardware.

NVIDIA Warp is a useful R&D candidate because it supports GPU kernels, geometry queries, PyTorch integration and differentiability. It should still be wrapped behind the backend interface. A CPU or simplified deterministic reference path is valuable for tests and environments without the required GPU.

Simulation output should include diagnostics:

- convergence status;
- maximum penetration;
- self-intersection count;
- inverted elements;
- strain statistics;
- seam error;
- time-step stability;
- energy history;
- warnings per panel or seam.

### 8.12 Stage L — Differentiable and iterative fit refinement

A coarse pattern should be refined against image evidence after draping it on the recovered or selected avatar.

A differentiable loop may optimise:

- panel dimensions;
- curve control points;
- ease allowances;
- seam ratios;
- garment placement;
- body shape within permitted bounds;
- camera parameters;
- selected material parameters;
- selected visual-shell offsets.

It should not begin by optimising every dense render vertex. That produces an ill-conditioned system and destroys garment structure.

Useful losses include:

```text
L_total =
    w_silhouette  * L_silhouette
  + w_landmark    * L_landmark
  + w_depth       * L_depth
  + w_normal      * L_normal
  + w_photo       * L_photometric
  + w_seam        * L_seam_consistency
  + w_collision   * L_collision
  + w_strain      * L_material_plausibility
  + w_pattern     * L_pattern_regularisation
  + w_symmetry    * L_symmetry
  + w_prior       * L_category_prior
```

A staged optimisation is safer:

1. camera and global alignment;
2. body pose/shape within trusted ranges;
3. coarse pattern measurements;
4. panel-curve refinement;
5. cloth parameters;
6. local appearance refinement.

Nvdiffrast or a compatible differentiable renderer can project the simulated garment into each source view and propagate image-space loss. A non-differentiable optimisation path should remain possible for stages where gradients are unreliable.

### 8.13 Stage M — Mesh analysis, cleanup and repair

Every imported or generated visual mesh should be analysed before it is accepted.

The report should cover:

- vertex/edge/face counts;
- connected components;
- open boundaries;
- non-manifold edges and vertices;
- duplicate vertices/faces;
- inconsistent normals;
- degenerate triangles;
- tiny disconnected components;
- self-intersections;
- extreme aspect ratios;
- hidden internal geometry;
- unexpected watertightness or thickness;
- scale and coordinate system;
- material slots and texture references;
- UV overlap/stretch where applicable.

Garments are often intentionally open surfaces. Therefore, “make watertight” is not a universal repair goal. A neck opening, sleeve cuff or hem must not be filled as though it were a broken statue.

Repair must be semantic-aware:

- preserve intended openings;
- keep accessories separate when useful;
- preserve visible silhouette;
- avoid merging layers;
- retain mappings to the raw proposal;
- record every destructive operation.

Useful implementation components may include libigl-style geometry processing, Blender in headless mode, xatlas for conventional atlas generation, and provider-specific tools such as TRELLIS.2's CuMesh. The choice should remain modular.

### 8.14 Stage N — Garment-specific retopology

The system should avoid treating “automatic retopology” as one operation.

There are three distinct targets:

1. **Simulation topology** — generated from the sewing pattern.
2. **Deformation/render topology** — dense surface that must follow the simulation mesh.
3. **Runtime fallback topology** — conventional simplified mesh for mobile or non-ZeroOne render paths.

For the dense render mesh, perfect animation-style quad loops are less important if a robust sim-to-render binding exists. The dense surface may remain triangulated as long as it is visually clean, correctly partitioned and bindable.

For the conventional fallback mesh, remeshing should preserve:

- silhouette;
- openings;
- semantic boundaries;
- texture fidelity;
- accessory separation;
- mapping to the simulation mesh.

A future learned garment retopology model could predict boundary-aligned flow, but it is not a prerequisite for the first vertical slice.

### 8.15 Stage O — UV strategy

Closy should use more than one UV concept.

#### Pattern UV

Every point on the simulation mesh already has a 2D panel coordinate. This is the canonical UV for:

- sewing-pattern editing;
- panel-space painting;
- grain-aware procedural detail;
- source image projection into known panels;
- material annotations.

#### Render atlas UV

The visual mesh may require a packed atlas for conventional rendering and export. This can be generated automatically, but should retain semantic island labels and texel-density rules.

#### Source-view projection coordinates

For evidence-preserving texture recovery, the system should store camera projections and view weights rather than immediately baking everything into one lossy atlas.

#### ZeroOne/GeomoTree coordinates

Procedural detail may use panel-space coordinates, local surface frames or a specialised virtual-texture coordinate system. It should not depend solely on an arbitrary generated atlas.

### 8.16 Stage P — Texture reconstruction and PBR material generation

Texture reconstruction should prioritise source fidelity.

Pipeline:

1. remove or estimate baked lighting from source images;
2. project each trusted view to visible surface regions;
3. weight views by angle, focus, occlusion and exposure;
4. normalise colour across views;
5. blend at seams with structure-aware masks;
6. preserve logos, text and pattern alignment;
7. inpaint genuinely unseen regions;
8. generate or estimate PBR channels;
9. retain a confidence map for every texel.

Material channels may include:

- base colour;
- normal;
- roughness;
- metallic;
- opacity/cutout;
- ambient occlusion where useful;
- thickness/transmission;
- displacement or height;
- anisotropy direction;
- fuzz/sheen parameters;
- confidence and provenance.

For most ordinary fabrics metallic should be near zero, but hardware such as zips or buttons may use separate material regions.

Generated inpainting should not overwrite observed brand marks or visible fabric features. A user-visible warning should be produced when important regions are inferred rather than observed.

### 8.17 Stage Q — Physical material inference

Visual texture and cloth physics are separate outputs.

A material descriptor should contain interpretable properties such as:

- fibre composition hypothesis;
- weave/knit category;
- approximate weight or GSM range;
- thickness;
- warp stretch;
- weft stretch;
- shear response;
- bending stiffness;
- damping;
- friction against skin and fabric;
- density;
- confidence interval;
- source evidence.

The system may infer these from labels, visual features and user metadata. Where certainty is low, it should choose a preset and expose an override such as:

- light cotton jersey;
- heavy cotton jersey;
- denim;
- satin;
- wool knit;
- polyester sports fabric;
- leather-like material.

Recent Image2Garment-style research suggests combining vision-language material descriptors with a smaller predictor that maps interpretable fabric attributes to measured physical parameters. Closy should follow this modular pattern rather than asking one black-box generator to invent both appearance and physics.

### 8.18 Stage R — Simulation-to-render binding

This binding is one of the most important assets in the entire system.

A straightforward binding stores, for each render vertex:

```cpp
struct RenderBinding
{
    uint32_t simulationTriangle;
    float barycentricU;
    float barycentricV;
    float normalOffset;
    uint16_t panelId;
    uint16_t flags;
};
```

At runtime:

1. retrieve the three deformed vertices of the bound simulation triangle;
2. reconstruct the render position from barycentric coordinates;
3. reconstruct a local frame;
4. apply the signed normal/tangent offset;
5. update normals and tangents or derive them from deformation;
6. render the dense surface or feed it to ZeroOne.

Alternative bindings include:

- cage coordinates;
- mean-value coordinates;
- tetrahedral embedding;
- nearest-surface binding with local frames;
- region-based affine transforms for rigid details;
- skeletal fallback weights.

The package should permit multiple binding types per component.

Validation must detect:

- render vertices bound to the wrong side or panel;
- large unsupported offsets;
- crossed seams;
- binding discontinuities;
- normal inversions;
- sliding across semantic boundaries;
- accessories that should not be cloth-bound.

### 8.19 Stage S — Garment layering, animation and fallback deformation

Long-term Closy outfits require ordered layers and collision policies.

Each garment should specify:

- layer class;
- preferred order;
- body clearance/ease;
- collision thickness;
- regions allowed to tuck or overlap;
- rigid/soft attachments;
- whether it can be partially hidden or removed in optimisation.

The full simulation path should use body and garment collisions. A cheaper fallback may use:

- transferred avatar skin weights;
- corrective blend shapes;
- pose-space deformation;
- pre-baked drape states;
- limited secondary motion.

This fallback is useful for low-end devices but must remain distinct from the authoritative simulation representation.

### 8.20 Stage T — Human correction tools

A production system needs compact correction interfaces for ambiguity.

Useful tools include:

- fix garment mask;
- declare front/rear/side view;
- mark neck, cuffs, hem and waist;
- choose between pattern hypotheses;
- drag garment landmarks;
- adjust length, width, sleeve and neckline controls;
- declare fabric preset;
- mark a logo or print as “must preserve”;
- identify a zip, button or pocket;
- approve or reject inferred rear texture;
- inspect collision and fit heatmaps.

Corrections should modify structured parameters, not destructively sculpt an anonymous mesh wherever possible.

### 8.21 Stage U — Quality gates and provenance

A garment should not be marked production-ready merely because every pipeline stage returned successfully.

Quality gates should cover:

#### Capture quality

- sufficient resolution and coverage;
- acceptable blur/exposure;
- consistent garment identity;
- adequate scale evidence.

#### Semantic quality

- category confidence;
- part completeness;
- seam graph validity;
- openings preserved.

#### Pattern quality

- valid closed panel boundaries;
- no self-intersections;
- valid seam references;
- compatible seam lengths or explicit easing;
- plausible dimensions.

#### Simulation quality

- settles without explosion;
- no severe body penetration;
- acceptable self-collision;
- bounded strain;
- seams converge.

#### Visual quality

- source-view silhouettes agree;
- visible texture regions are preserved;
- generated regions are identified;
- no major mesh defects.

#### Binding quality

- render shell follows representative poses;
- no cracks or seam tearing;
- stable normals/tangents.

#### Runtime quality

- memory and file sizes within profile;
- conventional fallback loads;
- ZeroOne derivative is optional and version-compatible.

Every stage should emit a report, and the final manifest should contain a concise quality summary rather than hiding warnings in logs.

---

## 9. Half Two: ZeroOne virtual-geometry and GeomoTree integration

### 9.1 ZeroOne's exact role

ZeroOne should become Closy's **asset foundry and high-detail geometry backend**.

It should receive an already validated Closy garment package and produce derived assets. It may improve geometry presentation, storage and rendering, but it should not be responsible for discovering the garment's canonical sewing pattern or deciding its cloth physics.

ZeroOne responsibilities:

- import and validate dense render meshes;
- preserve semantic and provenance attributes;
- generate cluster hierarchies;
- generate screen-space LOD data;
- generate streamable geometry pages;
- build visibility and occlusion structures;
- bake high-frequency detail;
- generate procedural details through GeomoTree;
- produce desktop-quality and mobile-quality derivatives;
- later support deformation-aware cluster bounds and rendering;
- generate a machine-readable processing report.

ZeroOne non-responsibilities:

- image segmentation;
- body estimation;
- sewing-pattern inference;
- seam semantics;
- fabric-property inference;
- primary cloth simulation;
- deciding which generative reconstruction is correct;
- replacing the conventional Closy fallback asset.

### 9.2 Integration should begin before “ZeroOne completion”

There is no useful requirement that the whole ZeroOne editor be complete before integration. Instead, ZeroOne becomes ready for each Closy phase when specific capabilities are stable.

The first integration gate requires only:

1. deterministic GLB or mesh import;
2. stable coordinate and unit handling;
3. preservation of vertex/face attributes or a mapping table;
4. headless processing;
5. deterministic output paths and reports;
6. conventional export or serialised cluster output;
7. no mutation of canonical pattern/simulation files.

Later gates add deformation and runtime streaming.

### 9.3 Headless asset-foundry interface

ZeroOne should eventually expose a command similar to:

```text
zeroone-process \
  --input garment.closygarment \
  --profile closy-desktop-quality \
  --output garment.closygarment/zeroone \
  --report garment.closygarment/reports/zeroone.json
```

Profiles may include:

```text
closy-desktop-quality
closy-desktop-interactive
closy-mobile-high
closy-mobile-balanced
closy-preview-static
closy-bake-only
```

The command should be resumable and return a non-zero exit code for fatal validation failures. Editor UI operation may remain available, but it must not be required for automated Closy jobs.

### 9.4 ZeroOne input contract

ZeroOne should consume only declared package assets, not search arbitrary folders and guess intent.

Inputs may include:

- `render/source_dense.glb`;
- `simulation/simulation_mesh.glb`;
- `binding/sim_to_render.bin`;
- semantic IDs and panel labels;
- material descriptors;
- pattern-space coordinates;
- optional detail masks;
- target runtime profile;
- topology hashes;
- coordinate-system metadata.

It should reject or explicitly migrate unsupported schema versions.

### 9.5 ZeroOne processing stages

#### Z1 — Import and invariants

- verify units, handedness, winding and transforms;
- verify topology hashes;
- check material/texture references;
- load semantic attributes;
- retain the original dense mesh unchanged as a source artefact.

#### Z2 — Dense geometry analysis

- cluster candidates;
- triangle distribution;
- spatial extent;
- open boundaries and semantic seams;
- tiny components;
- material splits;
- deforming versus rigid components;
- expected displacement/detail ranges.

#### Z3 — Detail classification

Separate detail that should remain geometry from detail that should be baked or generated procedurally.

Examples:

- silhouette-critical ruffles may remain geometry;
- tiny fabric weave usually becomes a material/normal detail;
- stitching may be geometry at close desktop range and baked for mobile;
- printed graphics remain texture;
- buttons/zips may remain separate rigid components;
- small wrinkles may be displacement or GeomoTree output.

#### Z4 — Cluster construction

Clusters should be spatially compact and respect:

- panel boundaries;
- material boundaries;
- rigid versus deforming components;
- seam discontinuities where necessary;
- local deformation coherence;
- normal/tangent continuity;
- page-size targets.

A cluster should never casually bridge unrelated garment layers because its conservative deformed bound would become inefficient and collisions/visibility would be misleading.

#### Z5 — Hierarchical LOD

The hierarchy should choose detail according to projected error rather than fixed object distance alone.

LOD generation must protect:

- silhouette;
- openings;
- seam lines;
- logo/texture registration;
- thin straps;
- small but identity-critical details;
- binding continuity.

The system should store error metrics and parent-child relationships in a versioned format.

#### Z6 — Geometry pages and residency

Output should include:

- page table;
- cluster-to-page mapping;
- dependency data;
- compressed geometry payloads;
- texture/material dependencies;
- memory estimates;
- streaming priority hints;
- fallback hierarchy roots guaranteed to be resident.

#### Z7 — Baking and procedural detail

ZeroOne/GeomoTree may generate:

- stitch rows following semantic seam paths;
- seam ridges and puckering;
- hems and cuffs;
- button thread;
- knit/weave relief;
- fabric fuzz or shell layers;
- fold enhancement;
- normal/height/roughness variation;
- distance-dependent detail.

These operations should be parameterised and recorded in a graph or manifest so that an asset can be regenerated.

#### Z8 — Runtime derivative export

Export at least:

- ZeroOne native virtual-geometry data;
- conventional simplified GLB fallback;
- mobile material set;
- thumbnails/turntable previews;
- processing report;
- compatibility/version metadata.

### 9.6 GeomoTree's role

GeomoTree can be highly valuable because garment detail is naturally procedural and semantically placed.

Rather than applying generic noise to an arbitrary mesh, GeomoTree operations should be driven by Closy metadata:

```text
Semantic seam path
      -> stitch generator
      -> seam ridge/pucker generator
      -> distance-aware geometry or baked map

Panel-space UV + grain direction
      -> weave/knit generator
      -> anisotropic normal/roughness
      -> optional close-range fibres

Garment landmark + mask
      -> button/zip/pocket detail
      -> rigid or cloth-bound attachment
```

Recommended GeomoTree garment nodes eventually include:

- `PanelBoundaryInput`;
- `SeamPathInput`;
- `GrainDirectionInput`;
- `GarmentLandmarkInput`;
- `StitchRow`;
- `OverlockStitch`;
- `SeamPucker`;
- `HemFold`;
- `RibbedCuff`;
- `KnitPattern`;
- `WovenFabricRelief`;
- `FuzzFibres`;
- `ButtonScatter/Placement`;
- `ZipTeethAlongPath`;
- `WrinkleField`;
- `BakeToNormalHeightRoughness`;
- `LODDetailSwitch`.

The first GeomoTree integration should be offline and deterministic. Dynamic procedural evaluation inside the Closy mobile app is a later optimisation, not the starting requirement.

### 9.7 Static versus deforming virtual geometry

A static high-detail garment is much easier than a cloth-deforming garment. Integration should progress through explicit levels.

#### Level Z-A — Static-pose preview

ZeroOne renders a dense garment in a fixed draped pose. Clusters and bounds are static.

This is useful immediately for:

- wardrobe thumbnails;
- product inspection;
- high-quality stills;
- asset validation;
- before/after ZeroOne comparison.

#### Level Z-B — Skeletal or coarse-cage deformation

The garment follows avatar pose using skinning or a coarse deformation cage. Cluster bounds can be updated conservatively from cage or bone influence bounds.

#### Level Z-C — Cloth-driven render-shell deformation

The low-resolution cloth solver updates the simulation mesh. Dense render vertices are reconstructed through the sim-to-render binding.

At this level the renderer must update:

- render positions;
- normals/tangents;
- cluster bounds;
- possibly geometric error estimates;
- visibility data affected by deformation.

#### Level Z-D — Deformation-aware streaming and LOD

The cluster hierarchy remains efficient during large folds and pose changes. Bounds, residency and projected error account for deformation.

#### Level Z-E — Mobile dynamic virtual geometry

Only after desktop correctness and profiling should a mobile-specific implementation be considered.

### 9.8 Recommended deformation architecture

Do not simulate the Nanite/ZeroOne mesh directly. Use the two-mesh system:

```text
SIMULATION MESH
regular, semantic, tens of thousands of vertices at most
        |
        | cloth solve
        v
DEFORMED SIMULATION STATE
        |
        | barycentric/cage binding
        v
DENSE RENDER MESH
hundreds of thousands or millions of vertices
        |
        | ZeroOne clustering/LOD/culling
        v
VISIBLE HIGH-DETAIL GARMENT
```

Potential implementation strategies are:

#### Strategy 1 — Deform all resident render vertices

A compute pass reconstructs every resident dense vertex from simulation triangles. It is straightforward and provides exact binding behaviour but may cost bandwidth.

#### Strategy 2 — Cluster-local deformation

Each cluster stores the simulation triangles or cage nodes that influence it. A coarse transform deforms the cluster, with residual per-vertex binding for accuracy.

#### Strategy 3 — Hybrid displacement

The simulation surface supplies large-scale deformation. Fine geometry is reconstructed from panel-space displacement, local procedural detail and texture rather than retaining every source vertex.

#### Strategy 4 — Bake distant deformation

Far LODs use a simplified mesh or displacement/normal approximation, while close LODs use the dense binding.

The architecture should permit several strategies by profile.

### 9.9 Deformed cluster bounds

Static bounds cannot safely cull dynamic cloth.

Possible bounds include:

- conservative union of influencing simulation-vertex bounds;
- cage-node bounds;
- per-frame GPU reduction;
- predicted maximum displacement envelopes;
- motion-expanded previous-frame bounds.

The bounds must avoid false negatives. Overly loose bounds reduce culling efficiency but are preferable to disappearing cloth.

### 9.10 Normals, tangents and cracks

Deforming independently streamed clusters creates risks:

- mismatched positions at boundaries;
- inconsistent normals;
- tangent discontinuities;
- LOD cracks;
- displacement gaps.

Mitigations include:

- shared boundary vertex identities;
- deterministic reconstruction from the same simulation binding;
- parent-child boundary constraints;
- skirts or stitch meshes where appropriate;
- normal reconstruction from deformed simulation frames;
- consistent material-space tangent generation.

### 9.11 ZeroOne output must remain derivative

The ZeroOne folder should be deletable and regenerable from canonical package data.

That means:

- canonical source images remain outside it;
- pattern and simulation topology remain outside it;
- ZeroOne outputs have explicit tool/version hashes;
- deleting ZeroOne output does not destroy the garment;
- a package validator can distinguish missing optional derivatives from a corrupt canonical asset.

---

## 10. The shared Closy garment package

### 10.1 Package concept

Use a directory during development and optionally a zip-like single-file container for transport.

Suggested extension:

```text
.closygarment
```

Internally:

```text
garment.closygarment/
  manifest.json
  provenance.json
  source/
    capture.json
    images/
    masks/
    cameras.json
    landmarks.json
  avatar/
    avatar_contract.json
    fitted_body.glb
    collision.glb
    body_regions.json
  semantic/
    garment_graph.json
    confidence.json
  pattern/
    pattern.json
    panels.svg
    preview.png
  simulation/
    simulation_mesh.glb
    rest_state.bin
    constraints.bin
    material_physics.json
    body_correspondence.bin
  render/
    source_dense.glb
    clean_dense.glb
    fallback.glb
    materials.json
    textures/
  binding/
    sim_to_render.bin
    binding_manifest.json
  zeroone/
    manifest.json
    cluster_hierarchy.bin
    geometry_pages/
    materials/
    baked/
  reports/
    capture_quality.json
    semantic_quality.json
    pattern_quality.json
    simulation_quality.json
    render_quality.json
    binding_quality.json
    zeroone.json
  previews/
    thumbnail.png
    turntable.mp4
```

Not every file is required in the first version. The manifest must distinguish required canonical files from optional derivatives.

### 10.2 Top-level manifest

Conceptual fields:

```json
{
  "schemaVersion": 1,
  "garmentId": "uuid",
  "displayName": "Blue cotton T-shirt",
  "garmentClass": "tshirt",
  "units": "meters",
  "coordinateConvention": "closy-gltf-rh-yup-v1",
  "canonicalAvatarContract": "closy-humanoid-v1",
  "status": "validated",
  "canonical": {
    "semantic": "semantic/garment_graph.json",
    "pattern": "pattern/pattern.json",
    "simulationMesh": "simulation/simulation_mesh.glb",
    "simulationMaterial": "simulation/material_physics.json"
  },
  "visual": {
    "denseMesh": "render/clean_dense.glb",
    "fallbackMesh": "render/fallback.glb",
    "binding": "binding/sim_to_render.bin"
  },
  "zeroOne": {
    "available": false,
    "formatVersion": null
  },
  "quality": {
    "overall": 0.82,
    "requiresReview": true,
    "warnings": ["rear_texture_inferred"]
  },
  "hashes": {
    "patternTopology": "...",
    "simulationTopology": "...",
    "renderTopology": "..."
  }
}
```

### 10.3 Coordinate and scale rules

The contract should define:

- metres as canonical units;
- a right-handed, Y-up convention aligned with glTF interchange;
- explicit front direction;
- counter-clockwise winding after import normalisation;
- transforms baked or declared consistently;
- avatar root at a known ground/hip convention;
- no implicit centimetre/metre guessing after validation.

Importers should record source conventions and conversions.

### 10.4 Stable IDs and hashes

Stable IDs should apply to:

- panels;
- seams;
- semantic edges;
- landmarks;
- material regions;
- garment components;
- avatar body regions.

Topology hashes should apply to each mesh. A binding is valid only when its declared source and target topology hashes match.

### 10.5 Provenance graph

The provenance file should describe derivation as a graph:

```text
source image hashes
  -> segmentation model/version
  -> mask hashes
  -> pattern model/version/seed
  -> pattern hash
  -> simulator/version/settings
  -> simulation mesh/state hash
  -> geometry provider/version/seed
  -> dense mesh hash
  -> binding algorithm/version
  -> ZeroOne build/version/profile
```

This is essential for debugging, model comparison, user deletion requests and future migrations.

### 10.6 Capability flags

A package may declare:

```text
has_pattern
has_simulation_mesh
has_physical_material
has_dense_render_mesh
has_dynamic_binding
has_skeletal_fallback
has_zeroone_static
has_zeroone_dynamic
has_mobile_fallback
has_verified_visible_texture
```

The app and tools should query capabilities rather than assume all assets are complete.

---

## 11. Recommended software architecture

### 11.1 Separate R&D/service layer

The AI and geometry-reconstruction pipeline should initially live in a Python-oriented service or sidecar rather than inside the React Native/mobile app or tightly inside the ZeroOne C++ editor.

Reasons:

- current 3D and vision models are primarily PyTorch/Python;
- model environments have large, conflicting dependencies;
- GPU workers need isolation;
- stages should be replaceable;
- jobs may execute locally, on a workstation or in the cloud;
- Closy mobile and ZeroOne should consume stable assets, not import ML stacks.

A later performance-critical library can move selected geometry/simulation code into C++/CUDA without changing the package schema.

### 11.2 Suggested repository/module boundaries

Exact placement should be decided after the work-mode chat inspects the repositories, but the logical structure should resemble:

```text
closy-forge/
  pyproject.toml
  src/closy_forge/
    cli/
    api/
    contracts/
    package_io/
    pipeline/
    capture/
    vision/
    body/
    semantics/
    patterns/
    geometry/
    simulation/
    fitting/
    materials/
    binding/
    providers/
      segmentation/
      body_models/
      geometry_generation/
      simulation/
    validation/
    reports/
  schemas/
  assets/
    reference_avatar/
    pattern_templates/
    material_presets/
  examples/
  tests/
    unit/
    integration/
    golden/
  docs/
```

### 11.3 Pipeline orchestration

Every stage should behave as an idempotent task:

```python
class PipelineStage(Protocol):
    name: str
    version: str

    def input_fingerprint(self, context: JobContext) -> str: ...
    def run(self, context: JobContext) -> StageResult: ...
    def validate(self, result: StageResult) -> ValidationReport: ...
```

A stage result should include:

- status;
- outputs;
- hashes;
- metrics;
- warnings;
- logs;
- elapsed time;
- model/tool versions;
- random seed;
- recoverability.

The orchestrator should support:

- resume after failure;
- cache by input fingerprint;
- rerun one stage and invalidate dependants;
- local synchronous mode for development;
- queue/worker mode later;
- cancellation;
- progress events;
- reproducible job export.

### 11.4 Provider isolation

Large model providers should run in separate processes or containers. Hunyuan3D, TRELLIS.2 and a cloth simulator may need different CUDA/PyTorch versions.

The core process should communicate through:

- local files and manifests;
- subprocess protocol;
- local HTTP/gRPC;
- or queued jobs.

Avoid importing every model into one Python environment.

### 11.5 CLI before full service UI

The first useful interface should be a deterministic CLI.

Long-term conceptual commands:

```text
closy-forge ingest <capture-folder>
closy-forge analyse <job-id>
closy-forge infer-pattern <job-id>
closy-forge simulate <job-id>
closy-forge reconstruct <capture-folder> --profile tshirt-v1
closy-forge validate <garment.closygarment>
closy-forge compare <garment-a> <garment-b>
closy-forge export <garment> --target glb-mobile
closy-forge zeroone <garment> --profile desktop-quality
```

The CLI gives the work-mode agent something testable without requiring immediate app screens or server deployment.

### 11.6 API shape

A future service may expose:

```text
POST   /v1/reconstruction-jobs
GET    /v1/reconstruction-jobs/{id}
POST   /v1/reconstruction-jobs/{id}/cancel
POST   /v1/reconstruction-jobs/{id}/corrections
GET    /v1/reconstruction-jobs/{id}/events
GET    /v1/garments/{id}/manifest
GET    /v1/garments/{id}/download
DELETE /v1/garments/{id}/sources
```

The mobile app should not need to know which foundation model produced a geometry proposal.

### 11.7 Storage model

Store large immutable artefacts in object storage or a content-addressed local cache. Keep searchable metadata in a database.

Recommended principles:

- content hashes as cache keys;
- immutable stage outputs;
- small manifests checked into test fixtures;
- large model weights outside repositories;
- user sources encrypted at rest;
- derived public/fallback assets separated from private capture sources;
- clear garbage collection of superseded intermediate meshes.

### 11.8 Observability

Record:

- stage timings;
- GPU/CPU memory peaks;
- model load time;
- queue time;
- mesh counts;
- simulation iterations;
- loss curves;
- validation outcomes;
- provider costs where applicable;
- user corrections;
- export sizes;
- runtime performance.

This turns R&D into measurable engineering rather than visual guesswork.

---

## 12. Recommended model/tool strategy

### 12.1 Do not train a large generic 3D model first

Training a competitive general-purpose 3D foundation model from scratch would consume the project while failing to solve garment semantics by itself.

Initial strategy:

1. integrate at least one local open model as a baseline;
2. optionally integrate one commercial API for comparison;
3. build Closy's own structured garment layer around those outputs;
4. train smaller garment-specific components first;
5. fine-tune or replace the generic geometry provider only when a dataset and benchmark justify it.

### 12.2 Current generic geometry candidates

As of the research snapshot:

#### Hunyuan3D 2.1

Useful properties:

- open model weights and training code;
- separate shape and PBR texture stages;
- local deployment path;
- practical baseline for fine-tuning experiments.

The official repository reports approximately 10 GB VRAM for shape generation, 21 GB for texture generation and 29 GB for combined operation. Treat these figures as model-version-specific, not permanent architecture requirements.

#### TRELLIS.2

Useful properties:

- 4B-parameter image-to-3D model;
- O-Voxel representation designed to handle open surfaces, complex topology and PBR attributes;
- training code and conversion pipeline;
- CUDA mesh post-processing tools.

The official implementation currently states Linux and an NVIDIA GPU with at least 24 GB memory as prerequisites. Its open-surface support makes it especially relevant as a visual proposal baseline for garments, but its output is still not a sewing pattern.

#### Meshy API

Useful properties:

- fast commercial baseline;
- single- and multi-image endpoints;
- current API support for one to four input views;
- GLB/FBX/OBJ outputs;
- PBR and high-resolution texture options;
- separate remesh, UV, rigging and other post-processing endpoints.

Its proprietary internals and provider terms mean it should be used through an adapter and never define the canonical package.

### 12.3 Garment-structure research directions

The most relevant research is not generic image-to-3D alone.

Important directions include:

- **GarmentCode/GarmentCodeData** — parametric sewing patterns and a large synthetic pattern/garment dataset;
- **Dress-1-to-3** — coarse sewing pattern plus multi-view diffusion and differentiable garment simulation refinement;
- **DressWild** — pose-agnostic, simulation-ready sewing-pattern reconstruction from an in-the-wild image using VLM priors;
- **Image2Garment** — joint geometry and interpretable material/physics prediction;
- **PatternGSL** — template-free structured language for complete sewing patterns and stitch topology;
- **Garment Particles** — a joint representation of 2D pattern coordinates and 3D draped geometry;
- **4D-DRESS** — real dynamic garment scans with semantic labels and fitted body models.

These should inform Closy's representation and benchmarks. Their code, weights, datasets and licences must be inspected individually before incorporation.

### 12.4 Vision and geometry utilities

Candidate supporting technologies include:

- a SAM-family model or fashion-specific model for segmentation;
- a monocular-depth model for initial depth cues;
- nvdiffrast or Kaolin-compatible differentiable rendering;
- NVIDIA Warp for GPU simulation/geometry experiments;
- libigl-style processing for geometry analysis and deformation;
- xatlas for conventional render-atlas UV generation;
- Blender headless scripting for import/export, baking and reference operations;
- glTF/GLB as a runtime interchange format;
- a separate structured JSON/binary format for information glTF does not express well.

Each is a replaceable implementation choice, not part of the eternal schema.

### 12.5 Model registry

Closy Forge should have a registry that records:

```text
provider ID
model ID/version
checkpoint hash
code revision
licence/terms reference
input/output capabilities
VRAM profile
supported platforms
known limitations
approved deployment scopes
```

A production job should never use an unregistered “latest” model without recording the exact resolved version.

---

## 13. Data strategy

### 13.1 Synthetic data is essential

Real photographs rarely arrive with ground-truth sewing patterns, material parameters, body shape and exact camera data. Synthetic generation is therefore required for supervised training and debugging.

A synthetic sample should ideally contain:

- garment category and semantic graph;
- exact sewing pattern;
- panel and seam IDs;
- body shape and measurements;
- body pose;
- cloth material parameters;
- settled and animated 3D garment;
- per-frame cameras;
- RGB renders under varied lighting/backgrounds;
- segmentation masks;
- depth, normals and optical flow;
- visibility/occlusion maps;
- pattern-to-3D correspondence;
- simulated defects and capture noise.

GarmentCodeData and its generation pipeline provide a strong reference and potential bootstrap source. Closy should also generate its own progressively richer dataset so its exact package schema is represented.

### 13.2 Real data remains necessary

Synthetic data does not fully reproduce:

- real fabric microstructure;
- manufacturing irregularity;
- unknown camera pipelines;
- complex logos and prints;
- wrinkles from storage and wear;
- layered clothing;
- unusual body/garment combinations;
- consumer capture mistakes.

Real data should come from:

- licensed research datasets;
- internally captured garments with known patterns and measurements;
- opt-in user corrections;
- retailer/manufacturer partnerships;
- controlled photogrammetry or 4D capture for selected garments.

### 13.3 Ground-truth capture programme

A small high-quality internal dataset may be more useful than a huge noisy scrape.

For each selected physical garment, record:

- flat front/rear/detail photos;
- worn multi-view photos;
- short motion sequences;
- actual panel pattern or carefully measured approximation;
- garment dimensions;
- fibre composition;
- fabric mass and thickness;
- simple stretch/bend measurements;
- reference body scan or measurements;
- high-quality 3D scan where possible;
- manually reviewed semantic graph.

Begin with a deliberately narrow garment family such as cotton T-shirts with varied necklines, sleeves, fit and prints.

### 13.4 Dataset versioning

Every dataset release should have:

- dataset ID/version;
- source and licence manifest;
- consent scope;
- train/validation/test split rules;
- garment and body distribution report;
- known biases;
- generation code revision;
- checksum manifest;
- deprecation/migration notes.

Test identities and physical garments must not leak into training via rendered variants.

### 13.5 Training curriculum

A sensible progression is:

1. synthetic T-shirt classification and landmark prediction;
2. T-shirt template-parameter regression;
3. multi-view parameter refinement;
4. fabric preset classification;
5. pattern-hypothesis ranking;
6. additional upper-body templates;
7. lower-body templates;
8. structured seam-graph prediction;
9. template-free panel generation;
10. garment-specific visual geometry fine-tuning;
11. dynamic material and drape prediction.

### 13.6 Smaller models to train first

The first proprietary Closy models should probably be:

- capture-quality scorer;
- garment category/part classifier;
- garment landmark detector;
- T-shirt pattern-parameter predictor;
- material descriptor predictor;
- pattern-hypothesis ranker;
- generated-region quality assessor;
- failure classifier.

These models create product value sooner and require far less compute than a general 3D foundation model.

### 13.7 Active learning

When users correct a mask, landmark, category or pattern parameter, the system may record an anonymised training example only with explicit opt-in and appropriate privacy controls.

Prioritise examples where:

- model confidence was high but the user corrected it;
- providers disagree strongly;
- validation fails repeatedly;
- garment categories are underrepresented;
- new trims or seam structures appear.

---

## 14. Evaluation and benchmarking

### 14.1 Every stage needs its own metrics

An end-to-end screenshot cannot reveal where a failure originated. Maintain stage-level benchmarks.

### 14.2 Capture metrics

- blur/focus prediction accuracy;
- view-label accuracy;
- foreground coverage;
- capture acceptance precision/recall;
- calibration error where ground truth exists.

### 14.3 Segmentation and semantic metrics

- garment-mask IoU;
- boundary F-score;
- part-mask IoU;
- landmark error normalised by garment size;
- component classification accuracy;
- seam/opening detection precision and recall.

### 14.4 Camera/body metrics

- reprojection error;
- pose-joint error;
- body measurement error;
- camera rotation/translation error;
- scale error;
- body/garment separation quality.

### 14.5 Pattern metrics

- panel count accuracy;
- semantic panel matching;
- seam-graph precision/recall/F1;
- boundary-curve distance;
- pattern-area error;
- garment measurement error;
- seam-length compatibility;
- topology validity rate;
- percentage of predictions that simulate without manual repair.

### 14.6 3D fit metrics

- multi-view silhouette IoU;
- Chamfer or surface distance where ground truth exists;
- normal consistency;
- landmark-to-surface error;
- body penetration area and depth;
- clearance/ease error;
- opening alignment;
- visible-region depth error.

### 14.7 Simulation metrics

- stable-settle rate;
- convergence iterations/time;
- maximum and mean strain;
- seam residual;
- body/self-collision count;
- inverted elements;
- frame stability under standard motions;
- energy drift;
- determinism tolerance.

### 14.8 Appearance metrics

- source-view reprojection error;
- visible-region perceptual similarity;
- logo/text preservation score;
- colour difference under calibrated conditions;
- seam visibility;
- generated-region artefact score;
- PBR relighting plausibility.

### 14.9 Binding metrics

- render/simulation correspondence error;
- seam crack magnitude;
- maximum binding offset;
- deformation inversion rate;
- normal/tangent continuity;
- pose-suite pass rate.

### 14.10 ZeroOne/runtime metrics

- cluster count and occupancy;
- page count and compression ratio;
- resident memory;
- peak streaming bandwidth;
- visible triangle/cluster count;
- culling efficiency;
- GPU frame time;
- deformation compute time;
- bound-update time;
- LOD popping/error;
- fallback GLB size and render time;
- mobile thermal/memory behaviour.

### 14.11 Provider bake-off

The same controlled capture set should be run through each geometry provider.

Record:

- success/failure;
- generation time;
- cost;
- geometry defect counts;
- silhouette fidelity;
- hidden-surface plausibility;
- texture fidelity;
- bindability;
- cleanup time;
- licence/deployment restrictions.

Provider selection should be evidence-based rather than driven by one attractive example.

### 14.12 Golden assets and regression suite

Maintain a small set of fixed assets including:

- basic T-shirt;
- printed T-shirt;
- loose shirt;
- sleeveless top;
- skirt;
- trousers;
- jacket;
- thin straps;
- layered outfit;
- difficult black/shiny fabric;
- occluded capture.

Every major change should regenerate or validate these and publish a comparison report.

---

## 15. Security, privacy, rights and licensing

### 15.1 Body and clothing imagery is sensitive

Images may reveal identity, body shape, home interiors, labels and location metadata.

Requirements:

- explicit consent and retention choices;
- encryption in transit and at rest;
- least-privilege access;
- audit logs for source access;
- source deletion independent of derived garment deletion where legally appropriate;
- no training use by default;
- no silent upload to third-party generation providers;
- redaction/cropping where possible;
- clear handling of minors and intimate garments.

### 15.2 External provider policy

A job should declare whether third-party APIs are permitted. The UI should not imply local/private processing when photographs leave Closy's infrastructure.

Record:

- provider;
- region if relevant;
- terms version;
- assets sent;
- deletion request/status;
- output rights;
- model/version.

### 15.3 Garment design and trademark rights

A user may reconstruct branded clothing, prints or copyrighted artwork. Closy should preserve user-owned/private wardrobe functionality while obtaining legal advice before enabling public resale, asset marketplaces or commercial redistribution of generated replicas.

### 15.4 Model and dataset licensing

Before adopting any model or dataset, review separately:

- code licence;
- weight/model licence;
- dataset licence;
- commercial-use permission;
- redistribution rights;
- generated-output rights;
- attribution requirements;
- patent considerations;
- dependencies with different terms.

Do not assume that an open GitHub repository or downloadable body model is unrestricted for commercial deployment.

### 15.5 Provenance and deletion

The provenance graph should make it possible to answer:

- which source images contributed to this asset;
- which external providers saw them;
- which trained models used the sample, if opt-in existed;
- which derived assets must be deleted when consent is withdrawn;
- whether a garment can remain after private body imagery is deleted.

---

## 16. Compute and deployment profiles

### 16.1 Development profiles

#### Profile D0 — Schema/CPU development

- no large model weights;
- deterministic sample assets;
- package I/O, validators and reports;
- unit and golden tests;
- suitable for CI.

#### Profile D1 — Local moderate GPU

- segmentation and smaller vision models;
- reduced-resolution geometry baseline;
- deterministic simulation tests;
- optional commercial API for dense proposals.

#### Profile D2 — 24 GB+ NVIDIA workstation/Linux worker

- TRELLIS.2-class local baseline;
- Hunyuan shape/texture stages depending on memory;
- GPU cloth simulation;
- differentiable refinement;
- dense binding and ZeroOne processing.

#### Profile D3 — Cloud research worker

- larger GPU memory;
- batch dataset generation;
- model fine-tuning;
- provider comparison;
- high-resolution asset baking.

### 16.2 Environment isolation

Use separate container/environment definitions for:

- core Closy Forge;
- segmentation/body worker;
- Hunyuan worker;
- TRELLIS worker;
- simulation/refinement worker;
- Blender/headless tools;
- ZeroOne executable.

A lockfile for one environment should not be allowed to destabilise every model worker.

### 16.3 Graceful degradation

A job should be able to complete at different quality tiers:

```text
Tier 0: Pattern + simulation + untextured fallback
Tier 1: Source-projected texture + conventional GLB
Tier 2: Dense visual proposal + dynamic binding
Tier 3: ZeroOne static high-detail derivative
Tier 4: ZeroOne dynamic high-detail derivative
```

The app can show capability and quality status rather than treating every missing premium stage as total failure.

---

## 17. Phased implementation roadmap

The phases are deliberately ordered to prove the hard representation and integration boundaries before expensive training.

### Phase 0 — Contract and deterministic harness

Deliver:

- Closy Forge project/module foundation;
- versioned package schema;
- package reader/writer;
- stable IDs and topology hashes;
- reference avatar contract;
- deterministic T-shirt pattern fixture;
- simulation/render/binding placeholders or simple generated assets;
- validators and reports;
- CLI;
- CI-friendly tests.

Success means one command builds and validates a complete deterministic sample package.

### Phase 1 — Deterministic T-shirt construction

Deliver:

- parametric front/back/sleeve/neck panels;
- seam graph;
- panel triangulation;
- simulation mesh;
- basic cloth settle on one fixed avatar;
- simple material preset;
- conventional GLB export;
- inspection renders and quality report.

No AI prediction is required yet. The purpose is to prove the canonical garment representation.

### Phase 2 — Capture and visual-understanding slice

Deliver:

- front/rear image ingestion;
- capture scoring;
- interactive/automatic garment masks;
- T-shirt landmarks;
- basic camera/view handling;
- editable correction records;
- visual report.

### Phase 3 — T-shirt pattern fitting from images

Deliver:

- estimate T-shirt template parameters from masks/landmarks;
- drape and compare to source views;
- optimise dimensions and curve controls;
- confidence and alternatives;
- pass/fail thresholds.

Begin with deterministic optimisation; train a parameter predictor later.

### Phase 4 — Texture identity recovery

Deliver:

- source-view projection;
- front/rear seam-aware blending;
- colour normalisation;
- visible-region confidence;
- logo/print preservation tests;
- controlled inpainting for unseen side/inside areas;
- PBR baseline.

### Phase 5 — Generic visual-geometry provider integration

Deliver:

- provider interface;
- null/manual provider;
- at least one local open model adapter;
- optional Meshy comparison adapter;
- raw proposal storage;
- geometry analysis and cleanup report;
- high-res visual shell alignment to the canonical garment.

### Phase 6 — Robust sim-to-render binding

Deliver:

- barycentric or cage binding;
- boundary/part safeguards;
- pose-suite validation;
- normal/tangent reconstruction;
- dense and fallback render paths;
- performance report.

### Phase 7 — Material physics inference

Deliver:

- fabric descriptor schema;
- preset classifier/selector;
- user override;
- calibrated material tests;
- dynamic cloth motion suite;
- confidence intervals.

### Phase 8 — Additional garment families

Recommended order:

1. sleeveless tops;
2. long-sleeved tops;
3. simple skirts;
4. simple trousers;
5. dresses;
6. shirts with openings/buttons;
7. jackets/outerwear;
8. layered and unusual garments.

Each family requires templates, semantics, capture tests and simulation validation.

### Phase 9 — Learned structured pattern inference

Deliver:

- synthetic training pipeline;
- template retrieval/ranking;
- structured pattern-program generation;
- grammar and geometry validation;
- variable panel counts;
- human correction UI;
- benchmark against template-only system.

### Phase 10 — ZeroOne offline/static integration

Deliver:

- headless ZeroOne processing command;
- package import/export;
- static cluster hierarchy;
- GeomoTree garment details;
- high-quality still/turntable profile;
- fallback preservation;
- deterministic reports.

### Phase 11 — ZeroOne deformation integration

Deliver:

- sim-to-render compute deformation;
- cluster influence metadata;
- deformed bounds;
- normal/tangent update;
- dynamic LOD correctness;
- representative motion benchmark;
- crack and culling tests.

### Phase 12 — Mobile/runtime optimisation

Deliver:

- remote/offline processing strategy;
- compressed runtime package;
- mobile fallback GLB;
- selected ZeroOne mobile profile if feasible;
- pre-baked motion/pose options;
- memory, battery and thermal tests;
- streaming/resume behaviour.

### Phase 13 — Personalised avatar and outfit layering

Deliver:

- licensed/commercial-safe body-model path;
- measurement/photo body fitting;
- body confidence and user correction;
- garment resizing/ease control;
- multiple garment collision layers;
- outfit-level quality and performance tests.

### Phase 14 — Closy-native trained models

Only after data and evaluation infrastructure are mature:

- fine-tune a visual geometry model for garments;
- train structured pattern generation;
- train physical material inference;
- train failure/quality models;
- compare every new model against external providers and deterministic baselines.

---

## 18. Cross-project integration gates

### Gate C1 — Closy canonical readiness

Required before serious AI provider work:

- valid pattern schema;
- valid simulation mesh schema;
- stable avatar contract;
- package validator;
- deterministic T-shirt package.

### Gate C2 — AI proposal readiness

Required before accepting generated meshes:

- raw/clean proposal distinction;
- geometry-analysis report;
- provider provenance;
- alignment and scale rules;
- rejection path.

### Gate C3 — Dynamic binding readiness

Required before high-res animation:

- stable sim topology;
- binding format;
- pose-suite tests;
- topology-hash validation;
- normal/tangent strategy.

### Gate Z1 — ZeroOne static readiness

Required for offline/static use:

- headless import/process/export;
- deterministic cluster output;
- package version handling;
- report generation;
- fallback preservation.

### Gate Z2 — ZeroOne dynamic readiness

Required for cloth-driven rendering:

- simulation influence data per cluster;
- deformation compute path;
- deformed bounds;
- crack-free boundary behaviour;
- performance instrumentation.

### Gate P1 — Product/private beta readiness

Required before processing real user captures:

- privacy controls;
- deletion flow;
- model/provider disclosure;
- clear confidence/warnings;
- correction path;
- failure-safe outputs;
- monitoring and rollback.

---

## 19. Risk register and mitigations

### Risk 1 — Single-view ambiguity

**Problem:** Rear panels, hidden seams and true depth cannot be uniquely recovered.

**Mitigation:** Guided multi-view capture; explicit uncertainty; category priors; alternative hypotheses; user confirmation.

### Risk 2 — Body/garment entanglement

**Problem:** The system explains body shape as garment volume or vice versa.

**Mitigation:** Fixed avatar first; body model abstraction; measurements; staged optimisation; body/garment collision priors.

### Risk 3 — Attractive but unusable AI mesh

**Problem:** Visual result contains fused layers, closed openings or chaotic topology.

**Mitigation:** Treat as visual proposal; canonical pattern separately; semantic validation; rejection and provider comparison.

### Risk 4 — Texture hallucination

**Problem:** Logos, text or patterns change, particularly on hidden/generated views.

**Mitigation:** Preserve observed texels; protected regions; provenance maps; user approval; generated-region labels.

### Risk 5 — Pattern inference scope explosion

**Problem:** Attempting all fashion categories prevents one reliable result.

**Mitigation:** T-shirt vertical slice; garment-family milestones; explicit unsupported-category handling.

### Risk 6 — Cloth instability

**Problem:** Bad seams, collisions or parameters cause explosions and penetrations.

**Mitigation:** deterministic fixtures; conservative presets; quality gates; solver diagnostics; progressive complexity.

### Risk 7 — Retopology destroys correspondence

**Problem:** Cleanup breaks texture, semantics or sim binding.

**Mitigation:** keep raw source; remesh only derivatives; topology hashes; transfer maps; semantic boundaries; validation.

### Risk 8 — ZeroOne coupling blocks Closy

**Problem:** App progress waits on experimental renderer features.

**Mitigation:** conventional fallback required; optional derivatives; capability flags; stable package boundary.

### Risk 9 — Dynamic clusters lose culling efficiency

**Problem:** Cloth folds create loose bounds and too many resident clusters.

**Mitigation:** deformation-coherent clustering; influence-aware bounds; hybrid distant LODs; profile-driven detail.

### Risk 10 — Dependency conflict

**Problem:** Large models require incompatible CUDA/PyTorch/toolchain versions.

**Mitigation:** process/container isolation; file/API contracts; model registry; minimal core environment.

### Risk 11 — Commercial licensing conflict

**Problem:** A research body model/dataset/model cannot be deployed commercially.

**Mitigation:** licence registry; abstraction boundaries; legal review; own data/implementation path; no silent dependency.

### Risk 12 — Privacy failure

**Problem:** User/body images are retained, trained on or sent externally without clear permission.

**Mitigation:** consent scopes in job manifest; local/external policy; encryption; deletion graph; no training by default.

### Risk 13 — Unmeasured visual progress

**Problem:** Development chases screenshots without knowing which stage improved.

**Mitigation:** golden assets; stage metrics; provider bake-offs; reproducible reports; regression thresholds.

### Risk 14 — Mobile expectations too early

**Problem:** Heavy generation/simulation is forced on-device before the pipeline is reliable.

**Mitigation:** headless workstation/cloud foundry first; runtime assets on mobile; graceful quality tiers.

---

## 20. Definition of success by product generation

### Research prototype success

- deterministic T-shirt pattern and simulation work;
- front/rear images can drive template fitting;
- visible texture is recovered;
- one dense visual shell can follow the simulation mesh;
- all stages are reproducible and reported.

### Alpha success

- several top categories work on one canonical avatar;
- capture guidance and correction are usable;
- geometry provider can be swapped;
- physical presets produce stable animation;
- conventional runtime exports are reliable;
- ZeroOne static preview is integrated.

### Beta success

- personalised avatars or measurements work within defined bounds;
- multiple garment layers are supported;
- confidence and failure handling are honest;
- ZeroOne dynamic high-detail preview works on supported desktop hardware;
- privacy/deletion/provider controls are complete;
- benchmark targets are met on a diverse test set.

### Production success

- users can reliably digitise supported garments without expert intervention;
- important visible identity is preserved;
- generated uncertainty is clearly managed;
- garment assets survive animation, resizing and app updates;
- runtime quality scales from fallback mobile to premium high detail;
- models and data are commercially deployable;
- the system improves through measured, consented data rather than opaque manual fixes.

---

## 21. Decisions that should be considered locked unless evidence changes

1. **Do not wait for ZeroOne completion to begin Closy garment R&D.**
2. **Do not build a second generic Nanite/LOD engine inside Closy.**
3. **Do not use the raw AI mesh as the canonical garment.**
4. **Use an explicit pattern/seam/simulation representation.**
5. **Use separate simulation and render meshes with a stored binding.**
6. **Use provider adapters for generic 3D models.**
7. **Keep ZeroOne outputs optional, derived and regenerable.**
8. **Start with one fixed avatar and one T-shirt family.**
9. **Use pattern space as a primary UV/semantic coordinate system.**
10. **Add model training after contracts, data generation and evaluation exist.**
11. **Preserve visible source evidence and mark generated regions.**
12. **Require deterministic CLI and validation before app/UI expansion.**

---

## 22. Recommended first implementation for the new work-mode chat

The first implementation should establish a **tangible deterministic vertical slice**, not merely empty interfaces and not an attempt at end-to-end AI generation.

### 22.1 Objective

Create the first version of the Closy Forge foundation that can build, inspect, package and validate a canonical T-shirt garment against one fixed avatar.

### 22.2 Required outcome

A developer should be able to run commands conceptually equivalent to:

```text
closy-forge demo build-tshirt --output out/demo_tshirt.closygarment
closy-forge validate out/demo_tshirt.closygarment
closy-forge report out/demo_tshirt.closygarment
```

The result should include:

- a valid package manifest;
- a fixed avatar contract/reference;
- a semantic graph for a short-sleeved T-shirt;
- parametric 2D panels;
- stable panel/edge/seam IDs;
- deterministic panel triangulation;
- a simulation mesh with panel-space UVs and semantic attributes;
- seam/constraint metadata;
- a simple render mesh or subdivided visual shell;
- a basic sim-to-render binding;
- conventional GLB outputs;
- validation reports;
- machine-readable topology hashes;
- unit/integration/golden tests;
- documentation describing how the sample is generated.

If a reliable cloth solver can be integrated cleanly within the inspected repository and task size, include a basic settle test. Otherwise, the first implementation should still encode the constraints and produce a canonical rest/assembly state without pretending a placeholder is full simulation.

### 22.3 First implementation should include

- schema versioning;
- strict validation and useful errors;
- deterministic seeds/settings;
- package reader/writer;
- CLI;
- topology/hash checks;
- small checked-in fixture assets only;
- no dependence on external API keys;
- no multi-gigabyte model downloads;
- no ZeroOne code changes yet;
- a future-facing provider interface only where it is exercised by a deterministic test provider;
- clear extension points for simulation and geometry providers;
- CI-safe tests.

### 22.4 First implementation should not include

- training a neural network;
- integrating every current 3D generator;
- arbitrary garment categories;
- personalised body recovery;
- production mobile UI;
- cloud queue/deployment;
- dynamic Nanite cloth deformation;
- a universal auto-retopology system;
- unbounded refactoring of Closy or ZeroOne;
- replacing existing stable app features.

### 22.5 Questions the work-mode chat must resolve by repository inspection

Before writing the coding prompt, it should determine:

- whether Closy already has a backend or monorepo location suitable for `closy-forge`;
- whether Python tooling already exists;
- how assets are currently stored and loaded;
- the current avatar format and coordinate convention;
- whether a separate repository/service is cleaner;
- which GLB and geometry libraries fit the existing licences/toolchain;
- whether the first solver belongs in Python/Warp, C++, Blender headless or a temporary deterministic assembly path;
- how CI is configured;
- how the package will later be handed to ZeroOne without coupling repositories prematurely.

### 22.6 Acceptance criteria for implementation one

The prompt generated in work mode should require at least:

1. Fresh checkout and documented setup succeeds.
2. The demo command produces the same structural output on repeated runs.
3. The validator accepts the generated package and rejects intentionally corrupted fixtures.
4. Panel, seam and topology IDs are stable.
5. The simulation mesh contains panel-space coordinates and semantic mapping.
6. The render binding declares and verifies source/target topology hashes.
7. GLB outputs load in a standard viewer.
8. No external service or private credential is required.
9. Tests cover schema migration/version rejection, package integrity and geometry invariants.
10. The implementation leaves a clear next step for capture/segmentation and actual cloth settling.

### 22.7 Suggested wording for the next chat request

The user can upload this file to the new work-mode chat and say:

> Inspect the relevant Closy repository or repositories and this master blueprint. Do not implement anything yet. Determine where the Closy Forge foundation should live, identify the existing avatar/asset conventions and then produce a complete, copy-ready implementation prompt for the first implementation in Section 22. The prompt must be repository-specific, substantial but bounded, test-driven, and must not touch ZeroOne yet except to preserve the future package boundary.

That next chat should then produce the actual coding prompt after repository inspection.

---

## 23. What implementation two should probably target

After the deterministic package exists, the next likely implementation should add a real basic cloth-assembly/settle path for the T-shirt on the fixed avatar, including:

- body collision;
- seam stitching;
- conservative cotton-jersey preset;
- settle diagnostics;
- output state persistence;
- penetration/strain validation;
- inspection render.

If implementation one already includes this robustly, implementation two should instead add front/rear capture ingestion, mask correction and T-shirt landmark extraction.

The exact order should be decided from the repository and implementation-one result rather than assumed now.

---

## 24. Research and implementation references

The following are the primary references used to ground this blueprint. Availability, versions and licences must be rechecked at implementation time.

### Generic image-to-3D and PBR asset generation

- **Hunyuan3D 2.1 — From Images to High-Fidelity 3D Assets with Production-Ready PBR Material.** Official repository: `Tencent-Hunyuan/Hunyuan3D-2.1`. Technical report associated with the repository.
- **TRELLIS.2 — Native and Compact Structured Latents for 3D Generation.** Official repository: `microsoft/TRELLIS.2`.
- **TRELLIS — Structured 3D Latents.** Official repository: `microsoft/TRELLIS`.
- **Meshy Image-to-3D and Multi-Image-to-3D API documentation.** Official Meshy API documentation; current model/provider behaviour is proprietary and versioned.

### Simulation-ready garment reconstruction and representation

- **Dress-1-to-3: Single Image to Simulation-Ready 3D Outfit with Diffusion Prior and Differentiable Physics.** arXiv:2502.03449.
- **DressWild: Feed-Forward Pose-Agnostic Garment Sewing Pattern Generation from In-the-Wild Images.** arXiv:2602.16502.
- **Image2Garment: Simulation-ready Garment Generation from a Single Image.** arXiv:2601.09658.
- **PatternGSL: A Structured Specification Language for Template-Free and Simulation-Ready 3D Garments.** arXiv:2606.24564.
- **Garment Particles: A 2D–3D Symmetric Garment Representation for Generation and Editing.** arXiv:2605.26391.
- **Stitched Embeddings: A Unified Latent Space for 3D Garments and 2D Sewing Patterns.** arXiv:2607.00829.
- **Natural Garment Language / training-free sewing-pattern estimation.** arXiv:2602.20700.

### Garment programming and datasets

- **GarmentCode: Programming Parametric Sewing Patterns.** ACM Transactions on Graphics, 2023. Official repository: `maria-korosteleva/GarmentCode`.
- **GarmentCodeData: A Dataset of 3D Made-to-Measure Garments With Sewing Patterns.** ECCV 2024; arXiv:2405.17609. The published dataset contains 115,000 examples across multiple garment categories and body shapes.
- **4D-DRESS: A 4D Dataset of Real-world Human Clothing with Semantic Annotations.** Official repository: `eth-ait/4d-dress`.

### Simulation, differentiable rendering and geometry processing

- **NVIDIA Warp.** Official repository: `NVIDIA/warp`; GPU-accelerated and differentiable kernels for simulation and geometry.
- **nvdiffrast.** Official repository: `NVlabs/nvdiffrast`; rasterisation primitives for differentiable rendering.
- **NVIDIA Kaolin.** Official repository: `NVIDIAGameWorks/kaolin`; 3D deep-learning and differentiable-rendering utilities.
- **libigl.** Official project/repository: `libigl/libigl`; geometry processing, parameterisation, deformation and remeshing utilities.
- **xatlas.** Official repository: `jpcy/xatlas`; conventional automatic UV atlas generation.
- **Blender command-line and Python scripting documentation.** Useful for headless reference import/export, baking and comparison operations.

### Body models and visual preprocessing

- **SMPL and related body models.** Official Max Planck body-model sites and licence documents. Model/software and generated-body licences must be assessed separately for Closy's intended commercial use.
- **Segment Anything model family.** Official Meta repositories; potential promptable mask provider, not a fashion-semantic solution by itself.
- **Depth Anything V2.** Official repository: `DepthAnything/Depth-Anything-V2`; potential monocular-depth cue provider.

---

## 25. Final architectural summary

The complete Closy system should ultimately behave like a specialist digital garment studio, not a thin wrapper around a generic image-to-3D endpoint.

```text
GENERIC AI MODELS
  propose visual shape, hidden detail and material appearance
                     |
                     v
CLOSY GARMENT INTELLIGENCE
  determines panels, seams, fit, physics, body correspondence and confidence
                     |
                     v
CLOSY SIMULATION + BINDING
  creates stable cloth behaviour and drives a separate detailed surface
                     |
                     v
ZEROONE + GEOMOTREE
  organises, enhances, streams, bakes and renders high-resolution detail
                     |
                     v
CLOSY PRODUCT
  delivers wardrobe capture, try-on, animation and scalable device quality
```

The defensible value is not merely generating more triangles. It is the structured bridge between real garment evidence, editable tailoring logic, physical drape, high-resolution appearance and practical runtime delivery.

The project should therefore begin immediately with the canonical garment contract and deterministic T-shirt vertical slice, while ZeroOne continues separately until its specific integration gates are ready.
