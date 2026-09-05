# Manual provider binding V2 sidecar

Scope: `manual_provider_binding_v2_development`, an exposed engineering lane.
The sidecar changes no V1 sources, old artifacts, canonical simulation topology,
source locks, evaluator entry points, or scientific budgets. No commit is made.
The parent owns launching the final 99-state evaluation and publication. The
subsequently authorized disjoint package/evaluation implementation is described
below; the sidecar does not launch that final evaluation.

## Public API

```python
from closy_forge.manual_provider_binding_v2 import (
    build_binding_v2, write_binding_v2, read_binding_v2, reconstruct_v2, check_rest,
)

bound = build_binding_v2(clean_meshset)
# bound.cage, bound.binding, bound.report; bound.simulation aliases bound.cage.
write_binding_v2(binding_path, bound.binding)
decoded = read_binding_v2(binding_path)
positions = reconstruct_v2(decoded_or_moved_cage_meshset, decoded)
receipt = check_rest(cage_glb_path, clean_glb_path, binding_path, bound.report)
```

`build_binding_v2(render, output_root=None)` also accepts a directory and writes
`output_root/binding/local_frame_v2.bin`. It does not write GLBs or assemble a
package. Use the unchanged shared `write_indexed_glb` for both geometries, preserving
vertex/primitive order and signed-zero convention. Input MeshSets are not mutated.
`check_rest` uses the shared GLB reader and hashing helpers but does **not** import
the binding producer, its decoder, its reconstruction, or its result arrays.

`check_rest` independently returns `restMaximumErrorMeters`,
`restP95ErrorMeters`, `restRmsErrorMeters`, a worst vertex/triangle witness,
content digests, counts, reduction ratio, and a derived status. If supplied,
declared metrics require both maximum and P95, with optional RMS comparison.
Invalid data or mismatched declarations raise `ValueError`; valid bytes whose
maximum exceeds 0.008 m return `status: fail`. There is no threshold slack.
The separate declared-metric float comparison tolerance is 0.000002 m.

## Representation And Limits

The old index-lattice stride-two approach is the narrow origin of the cage
sampling policy only. V2 identifies UV rows by geometry, sorts each row by U,
and validates all two-triangle fine cells, allowing either diagonal. V coordinates
may have float32-scale jitter (2e-7). Rows may taper and need not have uniform
spacing or fixed dimensions. Both grid dimensions must be at least three.
Vertex and triangle reorderings are supported. Mesh IDs are opaque unique
semantic panel/layer identifiers, never switches for orientation or shape.
Winding comes from actual faces in the UV chart. All fine faces must be valid
and consistently wound. Coarse face normals must agree with every covered fine
normal; folds that violate this assumption are explicitly unsupported.

Both axis endpoints and every second row/column form the initial visual driving cage.
A single bounded geometric refinement pass (declared below) may retain intermediate
samples. Its vertex count cannot exceed 60% of the dense
count on any panel. The actual nine shells retain only about 26.9%. The clean
dense topology, UVs, panel/material membership and vertex order remain untouched.
The shared indexed GLB writer derives normals and vec4 tangents from that unchanged
dense geometry; it also derives the coarser cage's own frame attributes.

Every render vertex selects the Euclidean closest point from at most eight
triangles in its same-panel coarse chart cells. This is a **restricted** closest
triangle search, not a global search over an entire folded garment. Only cells
covering that vertex's lattice coordinate are admissible. On a chart boundary,
weights may use only vertices of the corresponding boundary segment; corners
stay attached to their own corner. This prevents snapping to unrelated panels,
nearby layers, opposite cloth sides, or another opening edge. MeshSet does not
carry explicit cross-panel seam pair IDs: no physical seam-gap claim follows
from boundary retention. The parent must supply actual seam correspondence and
measure paired seams/openings separately.

For ordered triangle `(a,b,c)`, frame axes are `T=unit(b-a)`,
`N=unit(cross(b-a,c-a))`, `B=cross(N,T)`. The stored residual has components
along `(T,B,N)` in meters, not just along the normal. Runtime reconstruction is
`w0*a+w1*b+w2*c + dx*T+dy*B+dz*N`, with the frame recalculated from the supplied
cage. This is rotation-equivariant metric detail transport, not strain-scaled
detail or validated cloth dynamics. Degenerate frames fail instead of inventing
a normal. Geometry is quantized to the GLB float32 positions before binding;
weights/residuals are quantized before computing the producer's rest report.

Limits are three nonnegative influences, each at most one, normalized within
2e-7 after float32 rounding; **each** residual coordinate at most 0.03 m and
residual norm at most 0.03 m (2e-9 norm-rounding allowance only); 8192 total dense
vertices; 16384 triangles; 64 panels; 65536 metadata bytes; and 2 MiB per decoded
file. The parent still must enforce the unchanged **whole package** 2 MiB gate.
The search stores no dense-by-triangle matrix and allocates only bounded linear
mesh/record data plus up to eight candidates per vertex. These are engineering
input/storage caps, not a measured mobile-memory or runtime-performance claim.
Unsupported UV charts, holes, inconsistent connectivity, duplicate panel IDs,
incompatible folds, and oversize residuals are typed rejections, not fallback to
an identical dense cage. Unit A families are supported only if their actual
clean mesh satisfies this declared chart contract.

## Wire Format

All integers and floats are little endian. Header is `<8s7I32s32s32s32s`, 164 bytes:

1. Magic `CLSYBV2\0`, version 2, header size, record stride 36.
2. Record count, global cage triangle count, panel count, metadata byte count.
3. Shared cage topology, render topology, cage geometry, render geometry SHA-256
   digests, as four raw 32-byte values.

Metadata is canonical ASCII JSON containing the ordered panel table: `panelId`,
`materialId`, `renderVertexCount`, `cageVertexCount`, `cageTriangleCount`.
Each `<II6fI` record stores global cage triangle index, panel index, three weights,
three local residual coordinates, and a boundary mask (left=1, right=2,
bottom=4, top=8). Records are in original dense primitive/vertex order. Metadata
and declared counts are bounded before decoding records. Runtime checks topology
and semantic membership but intentionally permits changed cage positions;
the independent **rest** checker additionally checks both geometry identities.
The checker validates actual indexed geometry, tangent/normal layouts and
finiteness, edge incidence, boundary support, semantic membership and counts.
It rejects transforms not represented by the conservative shared GLB reader.

## Measured Witnesses

Read-only localization used saved `docs/evidence/manual_provider_c3_v1/packages`
clean/fallback GLBs and binding bytes. No historical evaluator was run. The old
maximum is at `manual-tshirt-01`, `panel.front`, local/global vertex 484,
UV `(0.8358311057, 0.6071428657)`, dense position
`(0.4907118082, 1.1692856550, 0.1204719990)` m. Dense minus old interpolation is
`(-0.0121511370, -0.0000000596, -0.0011725016)` m. Its tangential character makes
a normal-only correction inadequate. Published unquantized max is
0.01220758790967738 m; recomputation from saved float32 bytes is
0.012207575117394617 m. Four saved shells exceed 8 mm, retained below.

| Saved shell | V1 byte max (mm) | V1 byte P95 (mm) | V1 worst panel/local vertex | V2 producer max (m) | V2 max residual norm (mm) |
|---|---:|---:|---|---:|---:|
| manual-skirt-01 | 1.984105 | 1.496661 | front/320 | 3.03820e-8 | 1.909842 |
| manual-skirt-02 | 1.983558 | 1.450962 | front/328 | 3.65966e-8 | 1.978327 |
| manual-skirt-03 | 2.109254 | 1.464483 | front/284 | 3.76069e-8 | 1.874192 |
| manual-sleeveless-01 | 10.773280 | 2.040298 | front/484 | 5.45813e-8 | 9.938171 |
| manual-sleeveless-02 | 6.544923 | 2.365850 | front/435 | 5.74013e-8 | 6.541582 |
| manual-sleeveless-03 | 6.718756 | 1.830499 | front/448 | 5.70760e-8 | 6.201367 |
| manual-tshirt-01 | 12.207575 | 2.905548 | front/484 | 5.51310e-8 | 9.009677 |
| manual-tshirt-02 | 10.265804 | 2.631106 | front/610 | 5.58119e-8 | 8.997996 |
| manual-tshirt-03 | 11.882778 | 3.083737 | front/448 | 5.80959e-8 | 7.548569 |

V2 measurements in this table are lightweight producer rest-only diagnostics on
the already-published clean meshes, not package acceptance or a 99-state rerun.
All use 420/1566 cage/dense vertices except each `-03`, which uses 390/1450.
The maximum V2 producer P95 is 4.27127e-8 m. Host wall time for all nine
read/build/rest diagnostics was 6.726941 s; no mobile evidence is implied.
Follow-up actual-nine rest-only tests independently decoded freshly serialized
cages/bindings and the original saved clean GLBs. All nine passed, with maximum
5.8095877142487886e-8 m and maximum per-shell P95 4.2712688953318324e-8 m. Runtime
`read_binding_v2`/`reconstruct_v2` matched independent checker max/P95 within 1e-12 m.
The combined core/serialized-rest suite passed 42 tests in 10.39 s. These are not
motion-matrix results. The parent still derives final actual-nine metrics from
its final packages and retains all 99 motion rows separately.

## Small Test Inventory

Fixtures are exposed/tuning-used development inputs, declared in the new unit
test module before their execution: 7x8, 8x11 and 13x6 tapered grids, varying
diagonals, arbitrary vertex/face ordering, non-ID winding, close separate layers,
boundary/profile stress, rigid cage-frame motion, a planar closest-point witness,
and unsupported connectivity/fold cases. No source shell IDs drive production
behavior. Corruptions cover moved cage and render positions, stale topology,
cross-layer influences, negative/non-normalized/nonfinite weights, each residual
axis, record count overflow, missing vertices, boundary metadata, and forged
rest summaries even after rehashing the surrounding manifest. A failed 8.001 mm
case verifies that float comparison tolerance does not relax geometric acceptance.

The focused command is `python -m pytest -p no:cacheprovider
tests/unit/test_manual_provider_binding_v2.py` with `PYTHONPATH=src` under
`closy-forge`. No full corpus or unrelated tests are needed for this sidecar.
Ruff and targeted strict mypy are also run. Test receipts and any final count
are reported in the sidecar handoff, not asserted as full-stack acceptance here.

Final sidecar receipt (Python 3.12): **33 passed in 1.42 s**, Ruff check/format
clean, strict mypy clean for the three new source files. All existing tracked
files remain unchanged. V1's source-freeze verifier passes including its already
published `post_result_verifier_amendment.json` (three verifier-only replacements
at historical commit `a28a311`, not sidecar changes). The six shared protected
binding/GLB/triangulation/solver contract blobs match their repository lock exactly.

## Package And Evaluation Handoff

New implementation files are `manual_provider_binding_v2/package.py`,
`manual_provider_binding_v2/evaluation.py`,
`scripts/evaluate_manual_provider_binding_v2.py`, and
`tests/unit/test_manual_provider_binding_package_v2.py`. The binding codec/API
above remains unchanged. The parent commits all B files; they remain untracked
through the sidecar handoff.

Package APIs (import from `closy_forge.manual_provider_binding_v2.package`):

```python
result = build_package_v2(
    clean_path, semantics_path, output_root,
    source_id=source_id, family=family, source_identity=provenance,
)
verified = check_package_v2(output_root)
```

The default state sequence is the unchanged V1 `MOTION_STATES` (all eleven).
Tests may explicitly pass fewer states; the final evaluator cannot configure a
reduced baseline. Clean GLB and semantic source bytes are copied unchanged, not
reauthored or rerun through V1 cleanup. Package paths are:

- `render/clean.glb`: unchanged dense render input.
- `render/fallback.glb`: actual lower-resolution cage; **not** the dense output.
- `binding/local_frame_v2.bin`: V2 codec.
- `motion/{cage,production,reference}_states.f32.zlib`: bounded float32 XYZ states.
- `motion/manifest.json`: state IDs/parameters, raw payload digests and retained rows.
- `reports/{binding,rest,semantics,geometry}.json` and root `manifest.json`.

Runtime consumers should decode the cage with shared `read_glb_meshset`, decode
binding with `read_binding_v2`, and call `reconstruct_v2(cage_or_moved_cage, binding)`.
Positions are returned in dense render primitive/vertex order. `with_positions`
and bounded `read_positions` in `package.py` support replay of saved cage states.
No authoring parameters or dense hidden geometry are needed at reconstruction.

Production motion is generated only from the serialized cage using unchanged V1
low-resolution deformation, followed by V2 reconstruction. References use the
unchanged, separate V1 dense reference deformation on the saved clean GLB. Both
streams are float32-serialized before scoring. Package verification reconstructs
rest independently, rejects forged declared summaries even after manifest
rehashing, checks actual cage-driven production/reference motion, and verifies
inventory/geometry/tangent/semantic/runtime-path integrity. Whole-package size
remains capped at 2097152 bytes. Motion limits stay 20 mm maximum, 6 mm P95,
12 mm legacy UV-extrema error, and zero inverted/collapsed triangles.

The old UV-extrema statistic is named
`maximumUvEdgeReconstructionErrorMeters`, never a physical seam measurement.
Explicit `seamPairs` entries, when provided, contain a `seamId` plus `a`/`b`
objects with `panelId` and local `vertexIndex`. Actual gap and gap-change distances
are measured for those pairs only; saved baseline receipts have no such pairs
and are reported `not_available`. Boundary edge lengths/perimeters and triangle
validity are measured. Named neck/cuff/etc. geometry is explicitly unlocalized
without boundary-vertex mapping, not silently declared fully preserved.

### Parent-Only Final Command

Run under Python 3.12 from `closy-forge`, with `PYTHONPATH=src`:

```powershell
python scripts/evaluate_manual_provider_binding_v2.py --output .tmp/binding-final-v2
```

Optional explicit inputs are `--source-root` (default:
`docs/evidence/manual_provider_c3_v1/packages`) and `--unit-a-root` (default:
`.tmp/family-final-v2/build1`). `--resume` requires identical code, input and
protocol identities. Output must otherwise be fresh. No final run was launched
by this sidecar; `--help` was exercised.

Before executing geometry, the runner writes `protocol.json`,
`source_inventory.json`, `input_inventory.json`, and atomic `checkpoint.json`.
It retains two complete build roots, all 18 source/repeat attempts, the first
build's 99 rows in `baseline_rows.json`, and final `result.json`/`report.md`.
Exceptions produce eleven explicit failed rows for the same baseline source,
not a reduced denominator. Interrupted attempts remain failures on resume;
completed attempts are not retried. Source/input freshness is checked at the end.
Whole-saved-source manifest/input identities are verified read-only. The 17 V1
numeric thresholds and their operators are preserved, with misleading UV/opening
metric labels narrowed to their actual measured scope. Source inventory is the
static local import closure plus dynamically dispatched Unit A family modules.
Host CPU and wall time are measured; resident memory is explicitly not measured.

Four positive-input extras (9x9 dimensions, 17x13 density, 13x8 ordering, 9x11
paired-seam/open-boundary stress) retain a separate 44-state denominator. Three
negative cases cover holes, over-budget residuals and invalid seam endpoints.
Their definitions are predeclared in the protocol and marked exposed/tuning-used.
Input hashes are checkpointed before each extra package is built.

**Retained pre-refinement failures:** the 9-column dimension and seam/opening extras
pass rest binding but fail `step_left` P95 at 0.007918341249059907 m and
0.009397788159590435 m respectively. The synthetic reference has a discontinuous
left/right stride term at x=0, which crosses a coarse triangle influence span.
The 6 mm limit, cases, and initial failed packages remain unchanged. Protocol v3
records their exact manifest hashes and retained paths. No actual-nine motion
outcome is claimed before the parent runs it.

### Predeclared Sparse-Cell Repair

Before the next small-fixture run or final evaluation, protocol v3 declares
`broad_metric_cell.v1`: measure the initial stride-two cells using actual float32
3D positions. Trigger where a coarse triangle edge exceeds 0.14 m AND both chart
direction spans exceed 0.10 m. A direction span is the maximum of the two opposite
boundary chord lengths. Collect intermediate original rows and columns belonging
to triggered cells; retain samples on exactly one panel-wide axis, choosing the
fewest added cage vertices, then the shorter summed metric span over triggered
cells, then columns for an exact tie. This keeps a conforming lattice without
new vertices, T-junctions, identity rules, world-axis rules, or motion-state input.
Only one pass is allowed. Reject a result exceeding the unchanged 60% reduction
budget, rather than silently falling back to dense geometry.

These are **trigger** distances, not a promise that all final edges are under
0.14 m. Refining one axis reduces broad interpolation support area at bounded
storage cost. Thin cells already resolved in one direction are intentionally
unchanged. The exposed worst witnesses have edges 0.179175 m and 0.175606 m,
with chart spans approximately (0.105255, 0.145) m and (0.120223, 0.128) m.
Both occur at local vertex 3 of the second panel, UV (0.375, 0), across the
unchanged reference's discontinuous left/right stride term. Geometry-only
sampling cannot guarantee every future discontinuous deformation; the unchanged
motion gates remain mandatory. This criterion is explicitly development-tuned,
not held-out qualification. Across the actual nine clean shells, the maximum
smaller-direction span is 0.083781 m, so none qualifies for refinement.

Initial failed packages are retained read-only at
`.tmp/unit-b-package-tiny-01/test_predeclared_small_positiv0/package` and
`.tmp/unit-b-package-tiny-01/test_predeclared_small_positiv3/package`.
Their motion manifest SHA-256 values are respectively
`16fa26dc4462fd855791ad5f06d5fe64eef7dab014d546358153dca3d921d83d` and
`229b3b900f6f62fc79dba7af2e276cbfbc8777886eeb1222d0e4d35aa5587dd5`.
Protocol v3 also records the root manifest hashes separately.
The final 99 baseline and 44 positive-extra denominators remain unchanged.

First post-repair focused run: all 44 positive-extra motion rows pass, as do the
three expected negative rejections. In `step_left`, dimensions max/P95 changes
from 16.096454/7.918341 mm to 1.010976/0.992024 mm; seam/opening changes from
16.073141/9.397788 mm to 0.689265/0.687831 mm. Cages change from 50/162 to 90/162
vertices (55.556%) and 60/198 to 108/198 (54.545%). Their maximum errors over all
eleven states are 2.259573 mm and 1.567921 mm. Independently checked serialized
rest maxima are 2.395086e-8 m and 2.798081e-8 m. Density and ordering fixtures
remain unrefined and pass all eleven states. The unchanged original failure
packages remain under the paths above; new tiny packages are retained under
`.tmp/unit-b-refinement-tiny-01/test_predeclared_small_positiv{0,1,2,3}/package`.
These are exposed small-fixture results, not the final 99-state baseline matrix.

Final refinement verification before source freeze: **64 passed in 26.65 s**
across the two B test modules; Ruff check/format and strict mypy pass. This includes
all nine rest-only serialized tests, 44 small positive motion rows, three negative
cases, independent forged-metric/corruption checks, selective geometric refinement,
rigid rotation/reordering/renaming invariance, and a refinement budget rejection.
The checkpoint test still injects failures before geometry, not a hidden baseline
evaluation. Final tiny test artifacts use `.tmp/unit-b-refinement-frozen-01`.
All four extras' clean GLB and semantic input bytes were compared with their
original tiny packages and remain identical. Both original failed package
inventories and root/motion manifest hashes were verified read-only. Final whole
package sizes for dimensions/density/ordering/seam-opening are respectively
72239, 150591, 84648, 85449 bytes, all under the unchanged 2097152-byte gate.
Actual-nine cages retain zero refinements and exactly the original stride-two
row/column selections and counts; maximum independently serialized rest error
remains 5.8095877142487886e-8 m, maximum per-shell P95 4.2712688953318324e-8 m.
Source, tests, script and protocol are frozen for the parent's final run; this
receipt-only documentation update does not enter the evaluator's source closure.

Unit A probes use the saved nominal `tshirt`, `sleeveless_top`, and `simple_skirt`
packages via `validate_family` plus the strict V2 binding API, without recompiling.
Non-lattice topology is retained with an explicit unsupported reason. Other six
families are unsupported/not claimed. No canonical-to-V2 adapter was introduced
because the current independent checker contract is lattice-specific; it is not
weakened to create a false compatible row.

Focused package/evaluation tests: **19 passed in 7.17 s** before final documentation,
covering tiny serialized motion, deterministic packages, forged summaries/payloads,
path and decompression budgets, protocol limits, explicit seams, typed negatives,
known low-density failures, source inventory and interrupt/resume denominators.
The checkpoint test injects failures before geometry; it does not execute a hidden
99-state corpus evaluation. Ruff/strict mypy and CLI help are separate receipts.

## Final Parent-Run Receipt

The parent launched the frozen evaluator at `.tmp/binding-final-v2` using Python
3.11.4 and reported exit code 0. Read-only inspection of the saved `result.json`
and `report.md` confirms status `pass`; this documentation update did not launch
an evaluator, rerun tests, or alter source, tests, protocol, or result artifacts.
Earlier pending-run statements above describe the development chronology.

- Baseline: **99/99 rows pass**, zero failures, nine saved sources and eleven
  motion states. All **18/18 package attempts pass** across two retained builds;
  `deterministicTwoBuilds` is true. Repeat-build rows do not inflate the denominator.
- Separate positive extras: **44/44 motion rows pass**. All **7/7 extra cases pass**,
  comprising four positive cases and three correctly rejected negative cases.
- All **17/17 gates pass**; `limitsUnchanged` and `sourceAndInputsUnchanged` are true.
- Baseline serialized rest maximum: **5.8095877142487886e-8 m**; maximum per-shell
  rest P95: **4.2712688953318324e-8 m**.
- Baseline motion maximum: **0.01608670800963261 m**; maximum row P95:
  **0.0002271603414312708 m**, against unchanged 0.020 m / 0.006 m limits.
- Baseline UV-extrema maximum: **0.0003243232842949578 m**, against 0.012 m.
  This remains a reconstruction-error statistic, not a physical seam-gap measure.
- Maximum baseline package size: **528211 bytes**, below 2097152 bytes. Inverted
  and collapsed triangle totals are zero; vec4 tangent package rate is 1.0.

Recorded host elapsed time is 68.24128019995987 s, CPU time 65.6875 s. Resident
memory was not measured. These host measurements are not physical-mobile evidence.

Retained result identity and file digest (different digest definitions):

- `resultDigest`: `9b53a661891cec6ecaf31024e7a2cc3078ca5c313bba426bd9f28b5996de867b`.
- `result.json` file SHA-256: `fddf5aa31d6a886e22c4ac8e2422e9ed7c5e66c59ceed3f65a1cb460db70eb6c`.
- `protocolDigest`: `f4b9b51beaf8dd0544c0c9f6324604a01ab916354263a7ff40110b9e428b39e4`.
- `sourceDigest`: `bbc35b156fa626e1f628c8ed19cc1bd0359b328bf8a2bdab00dbb00a7d64ba1d`.
- `inputDigest`: `4ae141e83890feab989bc6368612f4ead484d933463a73d9be8c05f0ab57bd4d`.

The initial low-density failed receipts and their unchanged input identities remain
retained as documented above. Passing the repaired exposed extras does not erase
those failures or turn these inputs into held-out evidence. The three nominal
Unit A API probes remain `unsupported` with `binding_v2_unsupported_uv_lattice`;
the other six families remain unsupported/not claimed. Baseline physical paired
seams and named-opening mappings are unavailable, and no broad C3, canonical,
cloth, mobile, or scientific qualification follows. Publication is a separate
parent-owned step; this receipt does not claim a published commit or CI result.
