# Package Layering V1: Bounded Security Review

Date: 2026-09-05. **Frozen repair handoff: 109 passed, zero failures.** The parent
expanded this delegation to `package_layering_v1/contracts.py` and `solver.py`.
Only those two implementation files, `tests/unit/test_package_layering_security_v1.py`,
and this document were edited. Contact detection, matrix definitions, the parent's
original test file, the normal-hemisphere guard, frozen codecs, runtime V3, and demo
were not edited. No commit/staging or heavy/final-matrix evaluation was performed.

## Repairs And Current Receipts

The 22 reproduced failures below are resolved without weakening expectations or
changing any acceptance budget. Another 39 targeted cases extend the security file
from 65 to 104 tests; all five parent layering tests also pass.

- `contracts.validate_layer_binding(simulation, render, binding)` checks both decoded
  meshes, unique/matching panels, both topology hashes, exact triangle/panel/record
  counts, finite bounded barycentric weights, supported zero offsets/flags, and
  in-range indices whose referenced triangle and panel match each render vertex.
  This is explicitly the existing CLSYBND1 contract, not a new codec or B-parser fallback.
- `contracts.validate_specs()` and `validate_order()` validate all inputs before
  source reads, and are reused by direct assembly/solve and persisted context checks.
  Numeric values reject booleans, strings, nonfinite values and invalid shapes;
  layer IDs cannot contain the ownership delimiter. `LayerSettings` requires an
  actual bounded integer iteration count and retains all original numeric limits.
- `solver.combine()` sorts a copy of the layer list, validates source bindings before
  replacing hashes, checks source reconstruction, then validates assembled coverage.
  The input objects are not mutated. Public solve/measure/validate signatures are unchanged.
- Persisted vertex/triangle ownership must exactly equal the canonical ownership
  derived from decoded mesh panels, including lengths and represented source IDs.
  Material/clearance keys must exactly cover those sources; settings cannot silently
  omit fields or add ignored fields. This prevents filtering known cross-layer
  contacts by relabelling the triangles as one layer.
- `validate_output()` requires exactly seven inventoried payload/metadata files plus
  the manifest, with unique allowed names, exact integer lengths, hashes, and regular
  non-link/non-reparse entries. Duplicate rows, aliases, missing consumed files and
  unexpected files/directories reject. Manifest/context sources and profiles agree.
- Before-seam/opening measurements are independently recomputed from `input.glb` and
  the serialized constraints, then compared in full against `boundariesBefore`.
  Existing full before/after contact evidence checks and final drift rejection remain.
- The producer now emits `garment.outfit.<source-map-sha256-prefix>` instead of
  `outfit.<prefix>`, satisfying the runtime V3 garment namespace without adapting
  the source identity. A regression verifies the exact ID, unchanged source map,
  and valid manifest envelope. Existing probe outputs remain untouched and retain
  their original IDs; only newly produced outputs get the corrected namespace.

Frozen verification command, from the Forge root:

```powershell
$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'
py -3.12 -m pytest -o addopts= -q -p no:cacheprovider tests/unit/test_package_layering_v1.py tests/unit/test_package_layering_security_v1.py --junitxml="$env:TEMP/closy-layering-security-v1-garment-prefix.xml" --tb=short
py -3.12 -m ruff check src/closy_forge/package_layering_v1 tests/unit/test_package_layering_security_v1.py
py -3.12 -m ruff format --check src/closy_forge/package_layering_v1/contracts.py src/closy_forge/package_layering_v1/solver.py tests/unit/test_package_layering_security_v1.py
$env:MYPYPATH=(Join-Path (Get-Location) 'src')
py -3.12 -m mypy --follow-imports=silent src/closy_forge/package_layering_v1 tests/unit/test_package_layering_security_v1.py
```

Pytest exit 0: **109 passed in 5.74 seconds**, no errors/skips/xfails. Durable JUnit:
`C:/Users/zlerk/AppData/Local/Temp/closy-layering-security-v1-garment-prefix.xml`
(suite time 5.624 seconds). Ruff check and owned-file format check exit 0. Strict
mypy exits 0, no issues in six source files. Both layering test files were executed;
the parent-owned test file was not reformatted or included in the focused type check.
The initial post-fix 70-test green receipt is retained as
`C:/Users/zlerk/AppData/Local/Temp/closy-layering-security-v1-fixes.xml` (6.46 seconds).
The pre-prefix 108-test receipt remains in `closy-layering-security-v1-frozen.xml`
(6.79 seconds); it is historical, not the current producer snapshot.

Frozen SHA-256 snapshot:

| File | SHA-256 |
| --- | --- |
| `contracts.py` | `bd0140ab9e92c186c9468423e88eade5ff9a6972415e383e672c0bcb0b06c04a` |
| `solver.py` | `902c3aaf9af050ad472e5b6853059704b45173bf78b06da7830f07edbfbaaf90` |
| `test_package_layering_security_v1.py` | `d52a8474b0fcd50c063b7504e9572ec261fdf10be0555b1547aca36ac57310fa` |
| `contacts.py` (unchanged) | `32c976df22e83f19d2c3f1ef6ef0aa59e7086556d6eaca457320e576b236d1b8` |
| `matrix.py` (unchanged) | `211ad0ba7b6212531f4aff218f42c4a47a8571117c49d6b7d349ed2e33ef56a4` |

Security boundary: the externally trusted manifest digest remains the authenticity
anchor. Rehashing tests deliberately supply a new digest to test independent
structural/measurement consistency, not to claim that wholly replaced, internally
consistent source geometry and semantic declarations can be authenticated without
trusted provenance. `measure_persisted()` is a measurement API; callers needing the
trusted inventory check must use `validate_output()`.

## Read-Only Final Run Review

While the parent runs `.tmp/outfit-final-v1` (session 1937), all source and test files
remain frozen. This section is documentation only. The frozen contracts, solver,
security tests, contacts and matrix hashes above were rechecked unchanged. No CI,
additional matrix, or additional geometry experiment was launched during this review.

### Acceptance must inspect quality rows, not just process exit

By inspection, `scripts/evaluate_package_layering_v1.py:326` gates its exit code on
execution failures, unchanged sources and negative-control rejection, but not
`qualityPassed == 40`. Consequently exit 0 can coexist with `quality_failed` rows.
The parent must preserve/report each failed quality row and derive final 40-state
acceptance from all 40 terminal outcomes, not the evaluator exit code. Adjacent
midpoint rows use `terminal: executed`, which is not collision acceptance or CCD;
their measurements require separate interpretation. No evaluator change was made here.

### No-contact separation fallback is not a safe lower bound

By inspection, `contacts.py:142` returns the global broad-phase threshold when no
witnesses exist and labels it a lower bound. However, the actual narrow-phase
threshold is smaller: with both materials `(0.001, 0.001)`, these thresholds are
0.003 m and 0.002 m respectively. Parallel triangles 0.0025 m apart can therefore
have no witnesses while the fallback claims 0.003 m. This is a code-derived example,
not a new matrix result. Do not use that fallback as measured separation or a proven
global minimum in the final handoff. The readiness predicate uses residual deficits,
not this field. Correct the metric/label only in a separately authorized post-freeze
revision, retaining the current run's source identity and original receipts.

### Witness and resource scope

- Full before and after witness arrays remain in each inventoried `report.json` and
  are independently recomputed by validation. The matrix summary drops the after
  array only from its copied aggregate row; it does not erase the package evidence.
- The frozen grid rejects above 1,000,000 cell insertions. It does not cap the number
  of candidate pairs within populated cells, witness count, or serialized report
  size. Dense overlap can still produce quadratic pair growth. Bounded iterations
  and displacement do not establish bounded memory or physical mobile performance.
- There is no silent witness truncation in the layering path. A future resource cap
  must report an explicit unsupported/failed outcome rather than accept a truncated
  collision query. Existing depth witnesses are proximity/crossing projection
  deficits, not calibrated volumetric penetration or cloth physics.

### CI portability review, not a cross-platform execution receipt

`.github/workflows/closy-forge.yml` runs recursive unit shards on Ubuntu Python 3.11,
Windows Python 3.11, and Ubuntu Python 3.12. `ci/test_shards.py` automatically discovers
both layering test files under `tests/unit`; neither is excluded or platform-skipped.
The new security tests use `tmp_path`, generated tiny meshes, explicit little-endian
binary formats and standard-library APIs, with no local family package dependency,
Windows drive literal, subprocess, symlink privilege requirement or timing assertion.
Same-run determinism excludes timing-containing artifacts. Source syntax targets
Python 3.11, including the portable stat attribute fallback.

No concrete platform blocker was identified by inspection. The 109-test receipt is
Windows Python 3.12 only; all-platform acceptance still requires the actual CI jobs
and full-repository static checks after integration. No workflow or source edit was
made to manufacture a passing cross-platform claim.

## Historical Findings Before Repairs

Findings below preserve the reproduced failures and original line references,
ordered by impact. They describe the pre-repair snapshot, not current failures.

### P1: Triangle ownership can conceal known inter-layer contacts

`solver.py:399` trusts `context.triangleLayers` instead of checking it against the
serialized triangle/panel/vertex ownership. In a real persisted two-layer contact
fixture, relabelling both triangles as layer `a`, recomputing before/after reports,
and rehashing the inventory/manifest is accepted. The contact detector then filters
the known cross-layer pair as same-layer. Separately, a shortened triangle-layer
array is accepted for a clean no-candidate fixture because no candidate accesses its
missing element. A shortened vertex-layer array already rejects.

Required correction: validate exact label-array lengths independently of candidate
generation, validate IDs against the declared layer inventory, and independently
derive/compare ownership from serialized panel membership and triangle vertex IDs.
Do not fix this only by requiring nonempty contacts or witnesses.

Failing tests: `test_triangle_ownership_cannot_hide_known_interlayer_contacts` and
`test_missing_serialized_geometry_membership_rejected[triangleLayers]`.

### P1: Persisted binding validation accepts invalid influences and layout metadata

`solver.py:380` checks topology hashes and reconstruction error, but not the full
binding contract. Seven persisted mutations remain accepted: negative barycentric
weight, weights summing above one, nonzero legacy normal offset, panel index 65535,
nonzero flags, wrong simulation triangle count, and wrong panel count. The tests
write actual binding bytes, regenerate matching dense render bytes where relevant,
recompute the reported metrics, and rehash the complete envelope. Therefore an
unrelated stale report or checksum mismatch cannot mask invalid binding acceptance.
Stale simulation/render topology hashes and missing records already reject.

Required correction: validate counts, exact render-vertex coverage, both hashes,
finite bounded weights and their sum, triangle/panel ranges and membership, flags,
and the supported offset mode before reconstruction. The frozen legacy reconstructor
ignores normal offsets; accepting nonzero offsets is not support for those offsets.
Keep this correction in the successor lane, not the frozen codec.

Failing test: `test_rehashed_persisted_binding_must_be_valid_even_with_matching_render`
for the seven variants listed above.

### P1: Source assembly can replace an invalid binding identity with a valid-looking one

`solver.py:119` / `combine()` copies records and writes fresh topology hashes without
validating the incoming binding first. Direct calls accept stale simulation and
render hashes, negative weights, invalid weight sums, unsupported offsets and a
missing record. `load_layers()` normally validates source packages, but the exposed
assembly/solver API also accepts `LayerPackage` directly. Replacing hashes during
assembly must not make an invalid input look valid.

Required correction: validate source bindings before remapping; then validate the
assembled coverage and membership. Alternatively, enforce a genuinely checked
input boundary rather than assuming every dataclass instance came from the loader.

Failing test: all six variants of `test_combine_cannot_launder_invalid_source_binding`.

### P1: Inventory coverage is not exact

`solver.py:471` validates declared inventory rows, but does not require that every
consumed file be declared. Removing `render.glb` from the inventory and rehashing the
manifest is accepted while the validator still reads that file.

Required correction: require each consumed asset and metadata file exactly once in
the inventory, enforce an exact allowed file set, and verify sizes as well as hashes.
Do not treat a loop over whatever rows were supplied as complete coverage.

Failing test: `test_manifest_cannot_omit_file_that_validator_consumes`.

### P1: Before-boundary evidence is neither recomputed nor compared

`solver.py:464` now compares full before-contact metrics and witnesses, but does not
verify `boundariesBefore`. Rehashing a report with a forged 99 m before-seam gap is
accepted. Deleting all seam or all opening declarations and recomputing only the
after metrics also passes while the preserved before evidence describes the original
boundaries. This can erase evidence that a seam/opening was required.

Required correction: recompute and compare before-boundary metrics from input bytes
and require the original semantic seam/opening inventory to survive. Final drift
checks are insufficient if the declarations defining that drift can disappear.
After rehashing, an exact comparison against preserved before evidence should still
reject these inconsistent packages.

Failing tests: `test_rehashed_report_tampering_is_independently_rejected[before_boundaries]`
and both variants of `test_dropping_boundary_declarations_cannot_erase_prior_evidence`.

### P2: The direct combine API is not canonical under input permutation

`solver.py:128` iterates layers in caller order. Reversing the two input layers changes
assembled geometry hashes, remapped bindings and membership arrays. The parent's
recent sorting in `solve()` fixes its public solve path, which passes the serialized
permutation test; the directly exposed `combine()` API still differs.

Required correction: canonicalize in `combine()` as well, or make and enforce the
canonical-input contract there. The test intentionally excludes CPU/wall timings and
the timing-containing manifest from byte-for-byte determinism expectations.

Failing test: `test_combine_input_permutation_has_canonical_results`.

### P2: Iteration settings accept bool and nonintegral float

`solver.py:49` checks the numeric range but not the integer type. Both
`LayerSettings(iterations=True)` and `LayerSettings(iterations=1.5)` are accepted at
construction; the latter will fail later at `range()`. These should be typed input
rejections, not implicit bool coercion or downstream interpreter errors.

Required correction: require a non-bool integer before applying the bounded range.
Existing nonfinite material/transform values and out-of-budget numeric settings
already reject in the tested entry points.

Failing test: `test_invalid_settings_rejected_at_construction[kwargs2]` and `[kwargs3]`.

## Historical Passing Coverage And Scope

The pre-repair suite had 65 ordinary tests: **43 passed, 22 failed**, no skips/xfails or
errors. The failures represent the contracts above, not desired acceptance outcomes.
These expectations remain ordinary tests and were not excluded, xfailed or weakened
to obtain the current green result.

Passing coverage includes:

- Nonmatching vertex/face interiors with barycentric support, edge/edge interiors,
  edge-through-face crossing without VF/EE proximity, opposite-winding coplanar
  overlap, and genuinely disjoint control geometry.
- Policy-blocked contacts remain detected; the tiny unresolved case reports not ready
  with an explicitly non-collision-qualified input fallback.
- Canonical serialized solve results under layer permutation, excluding timing fields.
- Rejection of tested nonfinite material/translation inputs, invalid numerical budgets,
  NaN/infinite geometry, repeated/out-of-range indices, stale persisted topology hashes,
  missing binding records, missing vertex membership, and missing serialized vertices
  in each of input/simulation/render GLBs.
- Independently rehashed after-contact tampering, before-count tampering, erased
  witnesses with an executed flag, same-count fake witnesses, and forged before-depth
  metrics. The parent's full before-contact comparison already addresses those cases.
- Actual valid serialized geometry whose seam gap exceeds 8 mm is not ready. An
  independently isolated 25% opening-length drift also blocks readiness while seam
  error and displacement remain within their budgets and binding error stays tiny.
- The parent's small-correction guard preserves the posed-input normal hemisphere
  when a local step tries to cross 89 to 91 degrees. This regression passes; no
  relaxation of final orientation acceptance is suggested.
- Read-only inspection of the declared ten-case/four-state matrix includes all nine
  families. This checks its denominator, not execution or acceptance of those rows.

Fixtures contain at most four simulation triangles for serialized solver checks,
use two iterations, and never invoke family compilation, provider evaluation or the
final 40-state runner. All generated artifacts live in pytest temporary directories.
No source package inventory or historical result is modified. Measurements and
geometry are exposed development tests, not evidence of calibrated cloth, CCD,
articulated-avatar motion or physical mobile performance.

## Historical Reproducible Receipts

Final command, with `PYTHONPATH=src` and `PYTHONDONTWRITEBYTECODE=1`:

```powershell
py -3.12 -m pytest -o addopts= -q -p no:cacheprovider tests/unit/test_package_layering_security_v1.py --junitxml="$env:TEMP/closy-layering-security-v1-verification.xml" --tb=no
```

Exit **1**: **22 failed, 43 passed in 4.34 seconds**. Durable JUnit:
`C:/Users/zlerk/AppData/Local/Temp/closy-layering-security-v1-verification.xml`.
Earlier development receipts are retained as `closy-layering-security-v1-review.xml`
(61 cases, 19 failed) and `closy-layering-security-v1-review-final.xml` (65 cases,
22 failed). The later test revision additionally refreshes matching render/report
bytes for binding mutations so a stale report cannot create a false negative-control
pass. Expectations were strengthened, not relaxed.

Ruff check: exit 0. Ruff format check: exit 0, one file already formatted.
Focused strict mypy: exit 0, no issues in one source file, using
`MYPYPATH=<absolute Forge src directory>` and `--follow-imports=silent`.
The explicit source path avoids resolving the editable installation as an untyped
third-party dependency. No implementation lint/type changes were made here.

Reviewed implementation SHA-256 snapshot:

| File | SHA-256 |
| --- | --- |
| `contracts.py` | `50850e4bbade91ad8de5797787c2ec6229a4a675a17d3b88f90a31106c66dbb3` |
| `contacts.py` | `32c976df22e83f19d2c3f1ef6ef0aa59e7086556d6eaca457320e576b236d1b8` |
| `solver.py` | `45c7da7a373f8afa4c733db286bba47aac993188e404638520f533a81e339198` |
| `matrix.py` | `211ad0ba7b6212531f4aff218f42c4a47a8571117c49d6b7d349ed2e33ef56a4` |
| `test_package_layering_security_v1.py` | `87bbde3451326b317c03591db5526e98ff2ff10432fd184d4ed7ff37e3fc89a1` |

The parent changed solver canonical ordering and before-contact comparison during
the initial inspection. The final tiny run uses the snapshot above; its failures
must not be attributed to earlier versions of those already-corrected checks.

## Parent Handoff

The four-file repair sidecar is frozen and ready for the parent's planned cumulative
coverage on the integrated source state. The targeted contract failures are resolved;
no further contact/matrix edits are requested by this handoff. Runtime V3 files remain
available for parent integration and were not changed by this review or repair.

The actual 40-state acceptance remains **not run here**. If its contact correction
cannot resolve a declared case within the existing geometry/orientation/boundary
budgets, that row must remain failed. Passing software rejection tests or the normal
guard does not turn an unresolved contact case into accepted outfit physics.
