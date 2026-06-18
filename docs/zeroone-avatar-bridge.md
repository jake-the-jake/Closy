# ZeroOne Avatar Bridge

Closy owns the mobile wardrobe experience: user accounts, outfit selection, try-on UX, social sharing, saved looks, and product-facing avatar controls.

ZeroOne is the future high-quality rendering and simulation partner: avatar mesh processing, garment simulation, LOD, Nanite-style rendering, fit experiments, and production preview generation.

This bridge is intentionally a contract today, not a runtime dependency. The app must continue to work offline with bundled avatar assets and the emergency procedural fallback.

## Long-term Flow

1. Closy builds a `ZeroOneAvatarRequest` from the selected user, avatar source, body parameters, pose, outfit items, garments, camera, and requested outputs.
2. ZeroOne consumes that request through a future local engine bridge, offline export job, or native rendering backend.
3. ZeroOne returns a `ZeroOneAvatarResult` containing one or more outputs: rendered preview, optimized GLB/USDZ, fit diagnostics, simulation metadata, or recoverable errors.
4. Closy displays the preview, stores generated assets, or uses diagnostics to improve fit controls.

## Bridge Modes

- `local-placeholder`: Closy creates and validates requests locally only.
- `offline-export`: Closy writes a request artifact for a host-side tool or batch renderer.
- `future-native-engine`: a future native bridge calls ZeroOne directly from the app shell.

## Responsibilities

- Closy should never block Avatar Try-On startup on ZeroOne availability.
- Closy should treat the current Production Avatar as the default working bundled avatar until a better asset is installed.
- Missing realistic/stylised slots should remain explicit missing states, not silent procedural defaults.
- Procedural fallback is emergency/debug coverage, not the product path.
- ZeroOne outputs must be validated before replacing a known-good bundled avatar or rendered preview.

## Expected Outputs

- `previewImageUri`: a rendered still for product sharing or saved looks.
- `glbUri`: an optimized avatar/outfit asset for local rendering.
- `fitDiagnostics`: clipping, tension, collision, or garment confidence metadata.
- `simulationMetadata`: cloth/pose/runtime settings used to generate the result.
- `errors`: non-fatal or fatal issues that can be surfaced in dev tools.
