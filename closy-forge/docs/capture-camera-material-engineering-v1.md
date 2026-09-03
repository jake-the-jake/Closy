# Capture, camera, and appearance engineering v1

This development-only laboratory implements one composable capture-session model rather than five
incompatible mode silos. Scene condition, acquisition pattern, view role, subject condition, and
evidence tier are independent facets. The Phase-2 multi-view record remains backward-readable as
Mode C, but no duplicate legacy fields become new authority.

The frozen manifest is
`fixtures/capture_engineering_v1/development_acceptance_manifest.json`. It was committed before the
80-session validation corpus was generated or inspected. All derivatives of an identity group
remain in one partition, and every decode, QC, abstention, compile, topology, solver, and package
failure remains in its declared denominator.

Raster inputs are actual PNG/JPEG bytes decoded by the pinned Pillow/stdlib path. Video inputs are
actual RIFF AVI files carrying 24-bit uncompressed DIB frames. The small project-owned MIT decoder
is intentionally narrow, bounded, deterministic, offline, and listed in the local decoder SBOM. An
unsupported codec fails with a typed capability error; an image directory is never described as
video evidence.

Camera hypotheses derive from decoded pixels, masks, landmarks, declared view role, and an optional
coarse scale marker. Generator camera/crop values are evaluator-only. Source-to-panel appearance
uses mesh triangles, barycentric coordinates, role-aware visibility, and confidence-weighted source
sampling. Unknown texels use a deterministic fill with a separate generated mask. Novel views use
the independent ray/triangle renderer rather than the projection implementation.

All fixtures in this layer are project-authored synthetic development data. No real photograph,
private user, licensed body, physical material, D0 qualification, Research Prototype promotion,
Alpha, Beta, Production, GPU, or mobile evidence is claimed. The two in-repository renderers prove
engineering diversity only; a future D0 authority still requires independently hidden sources.
