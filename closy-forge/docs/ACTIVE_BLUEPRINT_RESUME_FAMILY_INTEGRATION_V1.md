# Family Integration V1: Safe Successor Resume Pointer

This new pointer does not replace or modify historical `ACTIVE_BLUEPRINT_RESUME.*` files.
The local baseline is PR66 `930b3da556c96e9ded52b6ee8df5620d4903c280`, tree
`1aee06f2d65bd66a08c63e30ad47ceb65c85a590`.
The integration worktree is `E:/apps/Closy-all-family-layer-integration-v1`.

## Current State

**Unit A evaluation and saved-artifact publication completed.** Output `.tmp/family-final-v2`
contains 54/54 valid builds, 27/27 deterministic pairs, 9/9 known-parameter capture checks,
and 18/18 typed rejections. The process returned exit 0. The 8 mm seam predicate still fails
38/54 builds; no cloth-physics or image-estimation qualification is claimed.
B/manual-provider binding and C/package-layer/runtime acceptance remain pending.

Read the [inspected PR66 Phase 0-14 baseline](blueprint_progress_v3.md) and the
[parent's execution/dependency record](family_binding_outfit_execution_v1.md). Do not follow stale
PR59/PR60-era actions from older active-resume files.

After the parent has received the evaluator's actual process exit and both final artifacts exist,
the current publication entry point will be
[Family Integration Progress](evidence/family_integration_v1/progress.md).
Until `publication_manifest.json` exists and its hashes verify, that destination is not a complete
publication. A returned publication identity means saved-artifact publication succeeded, not that
all garment quality gates passed. The evaluator may finish with failed rows; keep every one.

## Parent Publication Command

Run only **after** the 54-build evaluator and capture/control stages have terminated:

```powershell
Set-Location E:/apps/Closy-all-family-layer-integration-v1/closy-forge
$env:PYTHONPATH = 'src'
py -3.11 scripts/publish_family_integration_v1.py --evaluation-root .tmp/family-final-v2
```

The default output is the fresh `docs/evidence/family_integration_v1` directory. It must not exist.
The command never removes or overwrites an old publication. To retain an interrupted publication,
choose another fresh directory under `docs/evidence` using `--output`; record that changed destination
in the parent's current pointer. Do not silently reuse a partial folder.

The helper requires the declared 27 cases x two builds, 54 distinct terminal rows, a matching final
checkpoint, all nine capture rows, 18 negative controls, matching protocol/source identities and a
complete 27-case first-build family index. Merely finding `result.json` is insufficient because the
evaluator writes it before `family_index.json`. The helper does not manufacture a process-exit receipt;
the parent retains that separately.

## API And Outputs

The API is in [publish_family_integration_v1.py](../scripts/publish_family_integration_v1.py):

- `audit_repository(repo_root)` performs read-only local Git/blob preservation checks.
- `source_closure(forge_root, entry_paths)` resolves local Python imports through ASTs, including
  relative imports and package initializers; it executes no imported source.
- `prepare_publication(evaluation_root, *, forge_root, initial_root, prototype_roots)` validates
  completed saved inputs and returns `dict[str, bytes]` without writing output files.
- `publish(evaluation_root, output, *, forge_root, initial_root=None, prototype_roots=None)` validates
  everything first, then writes an exclusive fresh publication and returns its manifest.
- `write_fresh(output, documents)` is the low-level writer used by the pure tests; it is not a substitute
  for `publish`'s completion, source and artifact checks.
- `verify_publication(output, *, expected_identity=None)` checks the completion manifest, exact file
  inventory and content hashes. The writer runs this verification before returning success.

| Output | Contents |
|---|---|
| `protocol.json`, `source_inventory.json` | Exact original evaluator bytes. The source inventory remains its actual broad start-time snapshot. |
| `result.json` | All 54 rows with compact geometry/binding/seam audits and settling diagnostics; literal passed/failed/control counts; no physical or full Unit A acceptance grant. |
| `family_index.json` | All 27 first-build cases, actual identities/statuses and result-row references; no duplicated mesh payloads. |
| `capture_summaries.json` | All nine successful or failed round trips and their causal-control records; known parameters are explicit, pixel parameter estimation remains unsupported. |
| `retained_development.json` | Interrupted `.tmp/family-final-v1` protocol/checkpoint and source differences; both long-sleeve prototype audits and settling diagnostics. These are separate attempts, never subtracted from or relabeled as the final 54-run denominator. |
| `protected_sources.json` | Raw Git-blob proof for all 84 locked paths versus PR66, original historical object verification, checkout-byte classification, and existing tracked-tree check. |
| `provenance.json` | Exact input paths/hashes/sizes, relevant Unit A source closure digest, broad-inventory drift, current script/test hashes, and explicit freshness limitations. |
| `blueprint_current.json`, `blueprint_crosswalk.json` | V3 inventory and Phase 0-14 overview with Unit A additions distinct from retained PR66 evidence, plus the preserved 101/239 migration. B/C are pending; no overall percentage. |
| `progress.md` | Readable Phase 0-14 table and links to current results and retained development failures. |
| `publication_manifest.json` | Written last; hashes every output file. Its identity hashes the manifest without its own identity field, avoiding self-reference. |

GLBs, binding binaries, PNGs and per-vertex projection arrays are **hashed and checked at source, not
copied**. Compact summaries retain every declared outcome. Original raw evaluator artifacts remain
at their original paths with input hashes in provenance. Total emitted evidence is bounded to 8 MiB.

## Freshness And Preservation

The evaluator's start inventory enumerated all `src`, not only imported modules. Disjoint B/C additions
and reporting changes do not invalidate Unit A. The helper computes a conservative AST-reachable
closure from the evaluator plus the explicitly dispatched nine families' `parameters`,
`pattern_generator`, `semantic_graph` and `assembly` modules. Every reachable source must occur in the
original inventory with an unchanged hash. Unknown dynamic import loaders fail closed for review.
Changes and additions outside that closure are reported, not silently omitted or forged into a new
freeze. External Python/environment dependencies are not covered by this repository-only closure.

Evaluator/publication script and focused test hashes are recorded separately at publication time.
The evaluator did **not** freeze its launcher script at start, so a current script hash is not evidence
of that historical state. A current test-file hash is not a passing test-execution receipt.

Read-only inspection during sidecar development found **84/84 HEAD Git blobs byte-identical to PR66**
and no changes to existing tracked files. Seven checkout files match raw Git bytes; 77 differ only
by exact LF-to-CRLF checkout expansion. No normalization is applied to Git-blob comparison and no
protected checkout is rewritten. The old lock's `contracts/schema_registry.py` object already differs
from PR66; this pre-existing baseline difference is explicitly recorded rather than blamed on Unit A
or silently repaired. The original historical object remains separately verifiable.

The reachable Unit A closure inspected during development contained 102 `src` files, all matching
the running evaluator's snapshot; publication recomputes this rather than trusting that earlier check.
These checks run again before publication completes. Any substantive protected/old tracked change or
reachable-source drift blocks publication; no sealed experiment is rerun to repair a receipt.

## Scope Of Acceptance

Valid conventional triangles, stable topology and bounded canonical binding reconstruction are useful
Unit A results, not full seam, drape or physics acceptance. Opening checks measure sampled boundary
length, not full shape fidelity. The compiler retains `physicalQualityPassed=false`. Seam acceptance
against the existing `0.008 m` diagnostic is separately counted across all 54 planned rows, with
failed builds retained as not evaluated for that predicate.

Prototype long-sleeve seam gaps were approximately `0.285363 m` and `0.0440734 m`; both exceed `0.008 m`
despite valid geometry. The initial run retained three `KeyError:'garmentId'` build failures and stopped
with 51 of 54 declared builds not run. These are not replaced by green successor counts.

Capture outputs are project-authored renderer/round-trip tests supplied known parameters. They do not
establish image-driven parameter estimation. Units B/C need their own complete package-binding,
outfit, runtime, recovery and optional static evidence before their statuses change. CI, development
quality, scientific qualification and product readiness remain different questions.

No Y2 authority, seed, Strategy 3 retry, topology-strategy budget, canonical-candidate budget, private
capture, paid provider, ZeroOne modification or production deployment is authorized by publication.

## Focused Checks

```powershell
$env:PYTHONPATH = 'src'
py -3.12 -m pytest tests/unit/test_family_publication_v1.py -p no:cacheprovider
py -3.12 -m ruff check scripts/publish_family_integration_v1.py tests/unit/test_family_publication_v1.py
py -3.12 -m ruff format --check scripts/publish_family_integration_v1.py tests/unit/test_family_publication_v1.py
$env:MYPYPATH = 'src'
py -3.12 -m mypy scripts/publish_family_integration_v1.py tests/unit/test_family_publication_v1.py
```

Pure tests use inert saved-record fixtures, not real garment evaluators. Their dummy payloads validate
publication integrity/denominator behavior only; no geometry-quality claim is made from test fixtures.
