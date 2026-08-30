# ZeroOne mechanical reference motion v2

This profile localizes and replaces the invalid inherited Phase-11 input without changing Closy's
canonical garment authority. It is a derivative-only mechanical transport qualification, not cloth
physics and not blueprint Gate Z2.

## Source boundary

- Canonical `simulation/rest_state.json` remains the 218-source rest authority.
- The existing 1,248-destination production binding is applied unchanged.
- The MT1 transport surface expands 832 faces to 2,496 stable corner IDs and stores an explicit
  corner-to-logical map. Repeated corners do not become new binding authorities.
- All 832 faces are retained. The v1 processing path that removed 16 faces remains historical only.
- Canonical simulation, settled/render, binding, fallback, material, and package-digest identities
  remain unchanged.

## Motion and claims

The 13-frame project-authored analytic clip starts and returns at exact rest and combines translation,
spatially varying rotation, bend, and nonrigid deformation. Its normalized displacement and coverage
limits are frozen before the compiled run. It does not use PHY1-invalid solver states.

The independent Closy oracle reconstructs weighted destinations directly from request bytes. It
checks logical topology, stable intersection-pair identities, normals, tangents, corner cracks,
semantic-opening boundary distance, bounds/culling, continuous orientation, and exact rest/return.
ZeroOne's internal mechanical validator is recorded but is not used as MT1 or Z2 authority.

Admission of `zeroone/mechanical-reference-v2` means only that the scoped clean-reference MT1 profile
passed against the recorded processor binary. Phase 11 and global Z2 stay partial because no
solver-driven cloth trajectory was qualified. PHY1 and product-facing dynamic readiness are not
implied.

## Reproduction

```powershell
closy-forge zeroone prepare-mt1 <package> --json
closy-forge zeroone audit-representations <package> --output <audit.json> --json
closy-forge zeroone static <package> --invocation-root <root> --closy-sha <sha> <trusted flags>
closy-forge zeroone dynamic <package> --invocation-root <root> --closy-sha <sha> <trusted flags>
```

Use the exact authenticated ZeroOne workflow artifact named in execution evidence. A local candidate
binary or a stale v1 dynamic report schema fails closed.
