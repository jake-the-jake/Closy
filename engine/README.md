# Closy — native engine (first pass)

This folder is a **standalone C++17** module: avatar foundation, lightweight skeleton, optional OpenGL viewport demo. It is **not** wired into the Expo app; it is meant for a future native renderer or tooling.

## Layout

- `include/Closy/` — public headers (`Avatar`, `Scene`, `Mesh`, `Renderer`, `GlRenderer`, `Transform`, `Bone`, …)
- `src/` — implementations + `gl_procs.*` (minimal GL 3.3 function loading via `glfwGetProcAddress`)
- `examples/avatar_viewport.cpp` — GLFW demo: seven-part rigid mannequin driven by bones, pose presets **1–4** (T / A / Relaxed / Walk-like), shirt + trousers anchored to spine/pelvis, **B** skeleton, **R** reset camera, title shows pose
- `tests/avatar_smoke.cpp` — no GPU; validates spawn, clothing add/remove, bone count

## Build

```bash
cd engine
cmake -B build
cmake --build build --config Release
```

Outputs (Visual Studio generator):

- `build/Release/closy_avatar.lib` — static library
- `build/Release/avatar_smoke.exe` — headless test
- `build/Release/avatar_viewport.exe` — OpenGL demo (`CLOSY_BUILD_AVATAR_DEMO` defaults to ON)

Disable the demo:

```bash
cmake -B build -DCLOSY_BUILD_AVATAR_DEMO=OFF
```

Dependencies are fetched with **CMake FetchContent** (GLM, GLFW for the demo).

## Integration notes

- **Skinning**: No blended skinning — the body is **seven rigid parts** (pelvis, torso, head, limbs); each part uses its bone `worldTransform`. Poses edit bone locals only.
- **Clothing**: Each layer has an **anchor bone** + `localFromAnchor` (scale/offset defaults by `ClothingTag`); render uses `anchorWorld * localFromAnchor`.
