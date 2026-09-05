# Runtime Delivery V3 Sidecar

Unit C development implementation for the all-family integration prompt, section 5.3.
The V2 package/page/pose codec, receiver, archive format, source locks and historical
evidence are unchanged. V3 is an explicit envelope, not a redirected V2 import.
No canonical topology, static processor, cloth solver, collision or mobile acceptance
is implemented or implied here.

## Trust And Decoding

`RuntimeIdentityV3(garment_id, avatar_id, profile_id, provenance)` is supplied by the
caller. Provenance is an exact SHA-256 identity, not a permissive family-name match.
`manifest_identity()` hashes canonical metadata and the entire inventory while
excluding only its own `packageIdentity` field. The inventory includes the nested
V2 manifest and its real `.closy-forge-owned.json` marker. The original draft used
the wrong marker-name exclusion; V3 intentionally inventories and transports the
actual marker. Nothing in the frozen V2 codec was changed to accommodate this.

Load and prefix APIs require a trusted SHA-256 of the **manifest file bytes** from
outside the untrusted package. The package's self-declared digest is not a trust
anchor. Stream reception similarly requires `transfer_identity_v3(stream.manifest)`
from the trusted sender/channel. That identity covers expected asset metadata,
package-manifest hash, ordered dependencies, chunk inventory and aggregate hash.
This is integrity with external trust anchors, not a new signature/PKI scheme.

Full loads check exact inventories, portable paths, aliases, links/reparse points,
sizes, hashes and nested garment/profile/provenance. V2 decodes a verified temporary
snapshot. Prefix decoding verifies the same metadata and each complete entry before
adapting to the unchanged V2 fallback decoder. A prefix may be renderable while
driving data is still pending, but only its decoded conventional geometry is claimed
available. Pose/binding availability requires a successful full load.

GLB preflight bounds chunks, buffers, views, accessors, indices, attribute shapes and
allocation work before the immutable geometry decoder runs. Unsupported transforms,
instancing, morphs, skins and animations are rejected rather than silently ignored.
Decoded attributes, indices and triangles are audited; a valid GLB header is not
sufficient. Deformed cage and render triangles and coordinate bounds are also checked.

`load_or_compatible_last_good()` accepts only a separately trusted, fully validated
asset matching **all four** requested identity fields. A different valid garment,
avatar, profile or provenance is not a fallback. Recovery retains the failure reason.
Materialization validates in a private temporary directory before publishing a fresh
destination; invalid archives do not publish a partial package.

## APIs And Binding Codecs

- `build_runtime_package_v3(target, inputs=RuntimeV2Inputs(...), profile=..., identity=...,
  cage=Path(...), binding=Path(...), cage_poses=..., binding_codec=...)` builds the sidecar.
- `load_runtime_package_v3(root, expected=..., trusted_manifest_hash=...)` returns
  `LoadedRuntimePackageV3`, preserving V2 result fields and adding identity, decoded
  cage/render/binding, cage poses, outfit members and measured binding fidelity.
- `loaded.render_pose(pose_id)` reconstructs an actual `MeshSet` from decoded cage and
  binding bytes. Existing `write_indexed_glb` can export it with regenerated frames.
- `analytic_cage_poses_v3()` applies the four existing PR66 driver formulas to the
  decoded cage. `bound_pose_positions_v3()` derives dense positions from those drivers.
  These are analytic driver/binding-fidelity states, not articulated-avatar or cloth tests.
- `build_runtime_outfit_v3(..., members=...)` consumes actual combined outfit render,
  cage and binding files. It validates distinct member IDs and compatible avatars and
  profiles. Membership alone is not evidence of collision correctness; that remains
  the parent outfit producer's responsibility.
- `build_runtime_stream_v3(..., trusted_manifest_hash=..., chunk_size=...)`, `receive_v3`,
  `load_prefix_v3` and `materialize_v3` deliver the same packages. The receiver exposes
  `received_indices`, `missing_indices`, `resume_bytes_saved`, `receive`, `cancel`,
  `verified_prefix`, and `finalize`. These wrap the actual frozen `TransferReceiver`
  methods, including its length-before-hash validation order.

Explicit `bindingCodec` values:

- `CLSYBND1_zero_offsets`: Unit A. Both topology hashes, record/triangle/panel counts,
  finite barycentric weights and sum, triangle and panel bounds, semantic membership,
  zero offsets, flags and rest reconstruction are validated.
- `CLSYBV2_local_frame`: Unit B's stable serialized local-frame API. This calls
  `read_binding_v2`/`reconstruct_v2` and the independent `check_rest` on the original
  serialized cage/render/binding bytes. Geometry and topology identities, bounded
  weights/residuals, chart/boundary membership and the existing 8 mm rest gate apply.
  The parser is never guessed or retried under another codec.

## Predeclared Evaluation

The evaluator reads already-built fixtures; it never runs the family compiler or
cloth simulation. Default A input layout is
`.tmp/family-final-v2/build1/<family>/nominal`. All inventory entries are verified
read-only before use and again after a case. Missing inputs stay in the denominator.

The A matrix is exactly nine families, the two existing profiles, and two fresh
runtime builds: **36 rows**, four poses and first/middle/final resume checks per row.
The profiles remain `cpu-balanced-64k-v2` (65536/32768-byte source pages/chunks) and
`cpu-compact-32k-v2` (32768/16384 bytes). Source packages are reused, not rebuilt.
Representative B and actual whole-outfit sources each add four separately counted
rows (two profiles, two builds), without replacing an A family row.

After parent integration and once the host is free, the commands are:

```powershell
$env:PYTHONPATH = 'src'
py -3.12 scripts/evaluate_runtime_v3.py --declare-only --output .tmp/runtime-v3-final --representatives <parent-descriptors.json>
py -3.12 scripts/evaluate_runtime_v3.py --run --output .tmp/runtime-v3-final
```

These commands are documented for handoff; the actual 36-row matrix was **not run**
during this bounded delegation. Declaration without representatives is allowed, but
the result remains incomplete until both representative kinds are supplied in a new
predeclared run. No output is written into an input source directory.

The representative JSON is an explicit adapter, not guessed B/outfit package fields:

```json
{
  "cases": [{
    "caseId": "representative-local-frame",
    "kind": "binding",
    "root": "<absolute inventoried source directory>",
    "manifest": "manifest.json",
    "manifestSha256": "<trusted source manifest file SHA-256>",
    "garmentId": "garment.example",
    "avatarId": "avatar.example",
    "provenance": "<source packageIdentity or manifest file SHA-256>",
    "bindingCodec": "CLSYBV2_local_frame",
    "render": "<inventoried render GLB path>",
    "cage": "<inventoried cage GLB path>",
    "binding": "<inventoried binding path>",
    "members": []
  }]
}
```

For an outfit, use `kind: "outfit"`, an outfit `garmentId`, its actual combined
files, and at least two `members` containing `garmentId`, `avatarId`, `provenance`.
Its codec may be A or B. Optional `cagePoses` maps **all four** pose IDs to inventoried
V2 f32 pose payloads from the parent. If absent, the evaluator explicitly reports
analytic cage drivers. Optional `materials` and `zeroOneDerivativeDigest` are copied
as declared metadata. Conventional fallback is always selected, even when an optional
derivative digest is absent or unusable; this lane does not validate static ZeroOne.
`evaluate_case(case, output)` is the direct parent integration hook.

The now-available B package API declares `render/clean.glb` as its dense render,
`render/fallback.glb` as its cage, and `binding/local_frame_v2.bin` as its binding.
For that package, set descriptor `provenance` to its trusted manifest file SHA-256
(its producer calls the internal manifest identity `packageDigest`, not
`packageIdentity`). Its eleven-state compressed motion files are not V2 pose blobs;
omit `cagePoses` to use the four explicitly labelled analytic runtime drivers, or have
the parent serialize a deliberate four-state adapter. Do not relabel the eleven-state
B motion payload as the four-pose V2 format.

`protocol.json` pins code (conservatively all Forge Python sources), Python version,
input manifests, test IDs, historical V2 bytes, denominators and thresholds before
execution. One worker runs at a time with a 180-second timeout. Per-case process logs,
fsynced atomic receipts, process exit codes, checkpoint rows, test JUnit XML and final
result JSON are retained. Resume recovers completed worker receipts, checks freshness
and revalidates successful packages; missing exit receipts remain unknown. It never
silently reruns failed/interrupted expensive attempts. Ordinary repairs use a new
output root/protocol. No scientific attempt budget is consumed.

## Bounds And Claims

Frozen codec limits remain 4096 files, 64 MiB/file, 128 MiB total/decoded working set,
64 KiB decoded pages and 128x maximum expansion. V3 additionally bounds manifest JSON
to 1 MiB, decoded geometry to 262144 vertices/524288 triangles and coordinates to
10 m absolute, and requires triangle area above 1e-12 square metres. These are
predeclared development safety caps, not relaxed quality gates or mobile benchmarks.
The sidecar and marker consume space within the same file/byte caps.

Pose encoding retains V2's 1e-6 m evaluation gate. Cage/render binding comparison uses
Unit A's 2e-6 m float32 tolerance; B's independent rest gate remains 0.008 m without
adding tolerance to that threshold. Compression/page expansion, archive identities,
deterministic rebuilds, pose error, decoded reload and three resume outcomes are
measured from actual runtime bytes. Wall/CPU times and peak Python allocation are
**host measurements**, not RSS or physical-device memory. Physical mobile latency,
memory, battery and thermal fields stay `not_run`.

## Recovery Controls And Validation

V2's frozen 8/9 historical control result is preserved. Its cross-package control
used different chunk sizes, so length validation correctly returned
`transfer_chunk_size_mismatch` instead of the expected hash error. V3 independently
tests same-size bytes from another package (hash rejection), wrong-size bytes (length
rejection), incomplete reception (`transfer_chunks_missing`), and truncated/trailing
archives against their trusted aggregate (integrity rejection). A deliberately
rehashed truncated archive separately exercises the structural truncation contract.
No receiver validation order or historical expected string has been changed.

The focused suite also covers corruption/replacement, duplicate/stale/cancelled
transfers, quota/decompression bounds, metadata-only swaps, nested metadata swaps,
incompatible last-good assets, malformed GLBs, correctly enveloped invalid geometry
at load and prefix, binding bounds/hashes/weights, B's stale geometry, codec confusion,
optional derivative non-selection, atomic rejection, tiny outfit delivery and the
evaluator's read-only source hook/declaration behavior.

## Historical Delegation Receipts (2026-09-05)

Final focused command, with `PYTHONPATH=src` and `PYTHONDONTWRITEBYTECODE=1`:

```powershell
py -3.12 -m pytest -o addopts= -q -p no:cacheprovider tests/unit/test_runtime_v3.py tests/unit/test_runtime_delivery_v2.py --junitxml="$env:TEMP/closy-runtime-v3-focused-20260905.xml"
```

Exit 0: **52 passed in 47.96 seconds** (42 V3, 10 existing tiny V2 tests), zero
failures/errors/skips. JUnit receipt:
`C:/Users/zlerk/AppData/Local/Temp/closy-runtime-v3-focused-20260905.xml`.
The tiny tests include real serialized-B and combined two-panel outfit evaluator
hooks, not the parent production-sized representative evaluation.

`py -3.12 -m ruff check` on the four owned Python files: exit 0, all checks passed.
`py -3.12 -m ruff format --check` on those files: exit 0, four already formatted.
`py -3.12 -m mypy --follow-imports=silent` on those files: exit 0, no issues in four
source files. This is a focused strict check, not the final cumulative type suite.

Source SHA-256 receipts for this verification:

| File | SHA-256 |
| --- | --- |
| `package_v3.py` | `8a691dfe4a65d2a29289feb21ba0bc10bb767ffd8ffc77f9a2a026a5897adfdf` |
| `streaming_v3.py` | `cdc9f583a423f558f5ba8110ab844617b23f9a98b1b6a5da825b459f9151c45f` |
| `evaluate_runtime_v3.py` | `1d991616e0ac20e9a5834fe69bdcebbb7c36fb221e60b1c4ff7bedc3f259ea10` |
| `test_runtime_v3.py` | `678faee60e3cc5f029e211481d5c8887b28974998e6906400f232879661b22be` |

Eleven protected files were compared by `git hash-object` against their HEAD blobs;
all matched: V2 package/streaming and base receiver, shared GLB I/O, binary binding,
reconstruction, reference cloth solver, triangulation, binding contract, and the
historical static/runtime V2 protocol and result. This is a focused source-integrity
check, not a rerun of frozen scientific evaluations. No commits or staging were done
by this delegation, and no paths outside the five owned source/test/script/doc files
were manually edited.

Remaining: parent supplies representative inventoried B and actual whole-outfit
descriptors, then declares/runs the A36 plus separate representatives when the host
is available. Static processor, collision/demo, cumulative CI and physical-device
evaluation are deliberately not run here. Successor B/package integration source
may continue evolving; the final protocol must pin that final source state rather
than reuse these focused receipts as full-matrix evidence.

## Final Integrated Evaluation

The parent completed the final integrated run on Python 3.11. These later receipts
supersede the delegation's pending-work statements, not its historical source hashes.
No source was changed during the final run.

```powershell
$env:PYTHONPATH = 'src'
py -3.11 scripts/prepare_runtime_representatives_v3.py --binding .tmp/binding-final-v2/build1/manual-tshirt-01 --outfit .tmp/outfit-final-v2/outfit01/neutral --families .tmp/family-final-v2/build1 --output .tmp/runtime-representatives-v3-final.json
py -3.11 scripts/evaluate_runtime_v3.py --declare-only --output .tmp/runtime-v3-final-v2 --representatives .tmp/runtime-representatives-v3-final.json
py -3.11 scripts/evaluate_runtime_v3.py --run --output .tmp/runtime-v3-final-v2
```

All commands exited 0. Final result: 36/36 family rows, 4/4 manual-binding rows,
4/4 whole-outfit rows, 22/22 deterministic pairs, four poses and three resume checks
per row, and 43/43 focused runtime controls. `sourceFresh=true`; physical mobile
latency, memory, thermal and battery remain `not_run`. The final report carries the
whole outfit's failed source-quality status instead of promoting transport success
to fit success. Runtime derivatives were not accepted as dynamic ZeroOne output.

The preceding `.tmp/runtime-v3-final` remains retained as 44/44 passing under its
earlier source snapshot. An outfit no-contact reporting correction necessitated the
explicitly fresh final-code run above; its receipt is not silently overwritten.
