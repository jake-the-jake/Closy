# Family, Binding And Outfit Integration Results

This pass implements three versioned Forge development units without changing the
Expo avatar route or protected historical experiments. Software validity, garment
quality, scientific qualification and product readiness are separate outcomes.

## Publication And Validation

| Unit | Draft | Exact parent | Final head | Tree | Parent ahead/behind |
| --- | --- | --- | --- | --- | --- |
| A | [PR67](https://github.com/jake-the-jake/Closy/pull/67) | `930b3da556c96e9ded52b6ee8df5620d4903c280` | `ac5900f6c3688225d22d6d60e766bb87e5a1d1d0` | `ecd2d9388cfcb54d3042ca5a2f294c900956c131` | 1/0 |
| B | [PR68](https://github.com/jake-the-jake/Closy/pull/68) | `ac5900f6c3688225d22d6d60e766bb87e5a1d1d0` | `795b8962d27cccf3da0d003b007d90cce4b4b12e` | `49f3158a9086450aad420d6056573a27428a72b3` | 3/0 |

C is `codex/closy-forge-outfit-layer-runtime-integration-v1`, based exactly on final B.
Its final evaluations are complete. The draft is published to run required remote CI
alongside the already-running local cumulative suite, not to claim those pending
checks passed. Post-commit outcomes, immutable head/tree and local exit receipt are
recorded in the final PR body/handoff instead of a self-referential commit.

A [CI 33966852736](https://github.com/jake-the-jake/Closy/actions/runs/33966852736)
passed all 32 required Forge jobs. B's final
[CI 33969511161](https://github.com/jake-the-jake/Closy/actions/runs/33969511161)
passed all 32 required Forge jobs. The expected set is derived from the unchanged workflow: contracts,
15 unit-shard/platform jobs, three immutable-failure jobs, nine family jobs, two
integration shards, cross-minor digest comparison and aggregate. Supabase is a
separate external check, not a 33rd Forge requirement.

Earlier B runs remain retained: Windows paths in published JSON failed the existing
evidence scanner, then checkout CRLF conversion failed a strict report hash. Portable
path projections and narrowly scoped Git attributes fixed those defects; neither
the scanner nor hash checks were weakened. Historical reports were not rewritten.

Local static validation exited 0 for format, lint, strict mypy (551 source files),
schema freshness, unit/integration inventory and collection (1502 unique test IDs).
With `PYTHONPATH=src`, the full cumulative command is `py -3.11 scripts/validate_family_outfit_v1.py --output
.tmp/final-cumulative-v1`; its final `result.json` and JUnit are authoritative only
after process exit. The same existing immutable-failure node is assigned to its
dedicated required CI lane, not a new skipped test. The frozen Python source and
shard inventories are included in the evidence archive; its prepublication snapshot
explicitly says the cumulative process is running. No earlier green run substitutes
for that final receipt. Pure artifact packaging/extraction is verified separately.

The compact [evidence entry point](evidence/outfit_layer_runtime_v1/README.md) preserves
531 files losslessly in a 7378811-byte ZIP plus readable summaries/images. Expanded
publication identity: `98521d83eded89d3b3a22a2d39146d48174a0e106d7498241b559cd2dd8c06de`.
Archive envelope identity: `fcdf72052f42b414fb6799794da9229594d3046c4698a0bbf4566d1d213d7c8f`.
The first expanded-publication attempt rejected security-test parameter examples in
raw node IDs. That failure is retained; the successor publishes exact node hashes and
keeps raw IDs locally. No scanner relaxation, test removal or hidden credential export.

## Literal Results

| Measure | Previous result | Successor result |
| --- | --- | --- |
| Long-sleeved top collapse | 2 simulation / 8 dense triangles | 0 / 0 |
| Button shirt collapse | 4 simulation / 16 dense triangles | 0 / 0 |
| Jacket collapse | 2 simulation / 8 dense triangles | 0 / 0 |
| Nine-shell rest reconstruction maximum | 0.0122075879 m; 8 mm gate failed | 0.000000058096 m; unchanged gate passed |
| Actual package layering | Radial reference not general package evidence | 40/40 valid geometry, 0/40 fit-ready; failures retained |
| Conventional runtime geometry | 24/36 valid; 12 invalid | 36/36 valid plus 4/4 binding and 4/4 outfit rows |
| Cross-package corruption control | Rejected for length instead of expected hash | Separate same-size/hash, wrong-size/length and truncation controls |
| Static ZeroOne family acceptance | 6/9 | 9/9; static only |

A: 54/54 valid builds across 27 configurations, 27/27 deterministic pairs, 9/9
known-parameter capture/correction checks and 18/18 typed negative rejections.
The unchanged 8 mm paired-seam predicate passes 16/54 and fails 38/54. Numerical
triangle guards prevent collapse without deleting faces, changing canonical rest
connectivity or replacing garments. Capture fixtures supply known parameters; they
do not establish image-driven reconstruction for nine families.

B: 18/18 packages, 9/9 deterministic pairs, 99/99 baseline motion rows, 44/44 extra
motion rows, four extra positive cases and three typed negative cases. All 17 exposed
baseline gates pass. Maximum motion error is 0.016086708 m against 0.02 m; maximum
P95 is 0.000227160 m against 0.006 m. Maximum package size is 528211 bytes against
2097152 bytes. Baseline cage vertices remain about 26.82-26.90% of dense vertices;
two sparse extra fixtures require about 55% after bounded metric-cell refinement.
The independent checker reconstructs actual serialized bytes, including tangential
local-frame residuals; merely filling the old ignored normal offset could not repair
the measured error. UV-edge error is not claimed as physical seam separation.

Three actual Unit A interface probes reject unsupported non-lattice topology;
the remaining six are not claimed compatible with B's provider-binding codec.
Unit A's existing subdivision bindings remain valid. This is not global C3 acceptance.

C: all 40 outfit-state rows executed with zero implementation errors and unchanged
sources. All have valid geometry and zero orientation inversions, but all fail fit
acceptance. Thirty adjacent contact queries executed; 13/13 specified negatives
were safely rejected. Total evaluator wall time was 2353.49 s. Per-state accumulated
solver CPU was 1948.17 s and solver wall was 1964.48 s, excluding setup, midpoint
queries and controls. Maximum sampled cumulative process peak was 105472000 bytes;
this is Windows host RSS, not isolated per-row allocations or mobile memory.

Correction is not uniformly beneficial: summed crossings across the four states
increase from 582 to 675 for outfit01, 1742 to 1859 for outfit03, 2379 to 2490 for
outfit04 and 1041 to 1170 for outfit10. Other cases reduce crossings but still fail
the joint contact/seam/body/opening gates. The differently tessellated outfit09
reduces crossings from 410 to 284; it is not reported as recovered or ready.
Small separated and near-contact serialized fixtures pass focused controls, but
those do not substitute for the failed full-package matrix.

Final runtime `.tmp/runtime-v3-final-v2` exited 0 with `sourceFresh=true`: 36/36
family, 4/4 manual-binding and 4/4 whole-outfit rows; 22/22 deterministic pairs;
43/43 runtime controls. Every row retains four analytic pose and three resume checks.
The previously invalid 12 rows for long sleeves, button shirts and jackets now decode
valid geometry. Both existing CPU profiles remain unchanged. Outfit delivery retains
`sourceQuality.fitReady=false`; analytic encoding/binding fidelity is not skeleton,
cloth, dynamic ZeroOne or physical-device validation.

Static: nine families pass actual oriented-triangle/UV/material provenance and bounds
checks. Z4, Z5, Z6 and Z8 each pass nine; Z3 and Z7 each remain not_run for nine.
The earlier long-path attempt retains nine cook failures. The existing ZeroOne binary
was reused under an explicit new hash-reuse receipt, not rebuilt or represented as a
recovered historical build attestation. Dynamic integration gate Z2 remains not_run.

## Retained Development Failures

- A retains three initial integration failures and two numerical prototypes; no
  declared final configuration was removed from the 54-build denominator.
- B retains measured failed sparse-grid development attempts before bounded
  refinement; the nine historical shells remain exposed development inputs.
- C's first final attempt retains 17 quality failures and 23 incomplete/unstarted
  rows, plus an interruption receipt. A separate regression showed an overstated
  no-contact separation lower bound (5 mm reported for a 3.5 mm gap). The successor
  reports the valid 3 mm material-pair bound without altering solver thresholds.
- The first runtime matrix retains 44/44 valid rows and 22 deterministic pairs under
  its earlier source inventory. It is not substituted for final-code runtime evidence.
- All output images depict actual meshes. They remain coarse and visibly intersect
  in the outfit; the demo explicitly reports `outfitReady=false`.

## Corrected Phase 0-14 Overview

The [versioned inventory and crosswalk](evidence/family_integration_v1/blueprint_crosswalk.json)
preserve the historical 101/239-row reports. Phase membership now uses the nearest
explicit roadmap heading, not section 17; governing Deliver/Required context is
retained. Ambiguities remain reviewable. No overall completion percentage is given.

| Phase | Current supported scope | Remaining gate or dependency |
| --- | --- | --- |
| 0 | Contract, hashes, deterministic harness implemented in scoped fixtures | Broad acceptance not reassessed |
| 1 | T-shirt and all-family conventional construction validated | Seam/body convergence and physical drape |
| 2 | Real raster/video decoding and known-parameter integration | Better image inference, authorized data and privacy gates |
| 3 | Image-fitting implementation exists; historical route acceptance failed | Camera/fit accuracy and physical validity |
| 4 | Source-to-panel projection and causal pixel controls | Human review, hidden surfaces, real logos and general PBR |
| 5 | Authored manual-shell provider path | Licensed/approved learned providers and independent fidelity |
| 6 | Serialized local-frame binding repairs exposed nine-shell rest error | General non-lattice provider support; no global C3 |
| 7 | Material/solver implementation and failed recovery evidence retained | Better inference, measured fabric coupons and physical validation |
| 8 | Nine family semantics, 54 valid builds and supplied-parameter capture checks | All-family image-driven capture and simulation acceptance |
| 9 | Structured pattern/correction representation | Independent learned-pattern inference acceptance |
| 10 | Nine static processor outputs with decoded provenance/bounds audit | Unexecuted processor stages and wider integration qualification |
| 11 | Dynamic request/reference paths retained | Admissible cloth motion and dynamic ZeroOne Z2 readiness |
| 12 | V3 metadata trust, decoded fallback, 44 runtime rows, pose/reload/resume | Physical device latency/memory/thermal/battery not_run |
| 13 | Actual package contact/correction and separate semantic layers | Collision/seam-converged outfits; licensed bodies and personalized fit |
| 14 | Bounded advisory models retained | Authorized training data, compute and independent model evaluation |

The latest generated B/C evidence overlays supersede A's pending-unit fields;
historical acceptance fields stay labeled historical rather than being overwritten.
Passing CI does not promote any of these phases to scientific or product qualification.

## Tested Inspection

From `E:/apps/Closy-all-family-layer-integration-v1/closy-forge`:

```powershell
$env:PYTHONPATH = 'src'
py -3.11 scripts/demo_family_outfit_v1.py --families-cache .tmp/family-final-v2/build1 --output .tmp/demo-final-v1
```

The command completed with exit 0. Use a fresh output directory for a new invocation.
The optional cache is verified by actual compiler-closure and package hashes; omit
it to build all nine nominal packages. Inspect `.tmp/demo-final-v1/index.html`,
`garments/<family>/render/fallback.glb`, `outfit/render.glb` and the three PNGs under
`inspection`: `family_contact_sheet.png`, `sleeve_before_after.png` and
`binding_before_after.png`. All three images were opened and visually inspected.
The sleeve before view contains exact retained failed-triangle witnesses only, not
an invented whole original mesh. The binding view uses decoded old/new cage data.

## Boundaries And Next Step

All 84 protected blob identities have matched the PR66 baseline in checks so far.
No protected helper, scientific evaluator, old golden or historical result was
redirected. No main push, merge, ready conversion, force-push, branch/worktree deletion,
Expo change, ZeroOne source/binary change or new service/model download was performed.
The primary dirty worktree remains untouched. The prepublication preservation check
also confirms the exact read-only ZeroOne source/tree/executable and unchanged main;
the post-commit handoff repeats the live-ref checks.

Y2 remains `preseed_scientific_protocol_invalid`; AUTH1 unused, Strategy 3 consumed,
topology-strategy budget zero and canonical-candidate budget one. There is no new
Research Prototype, global C3, PHY1, dynamic Z2, physical mobile, Alpha/Beta or
production grant.

The next technical step is bounded numerical seam-converged initial dressing and
coupled contact correction on the existing canonical topology. Start from the retained
actual outfit witnesses and report both reductions and regressions. Do not introduce
another canonical strategy, hide contact failures, or treat transport fidelity as cloth
physics. Generalized non-lattice provider binding is a separate remaining dependency.
