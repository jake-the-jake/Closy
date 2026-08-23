# Active Blueprint Resume

This file is a recoverable checkpoint for the continuous Closy master-blueprint work. It records evidence ancestry and next actions without trying to cite its own future commit SHA.

## Current State

- Active blueprint checkpoint: `REPO-HYGIENE-CI-DIAGNOSTICS`
- Exact subtask: replace broad Forge failure-artifact upload with strict privacy-safe diagnostics before raster ingestion.
- Current branch: `codex/closy-forge-phase-0`
- Evidence commit SHA: `e02b85a5f6f2e165c7a0dec2777ff10531048d1b`
- Record based on SHA: `e02b85a5f6f2e165c7a0dec2777ff10531048d1b`
- Draft PR: `https://github.com/jake-the-jake/Closy/pull/1`
- Last remote green evidence: GitHub Actions run `32658750731`, Ubuntu and Windows Forge Python 3.11 jobs passed at commit `7c649178cea49542ff759de51a79c959c5c1e15c`.
- Last local package digest before this resume record: `f84091eb6bdd3f9e42e40a7319580cbf24699f41b1e3b7b306a2a564087771e0`

## Current BP-46 Truth

- `meshStitchOrWeldExecutionRun=true` is backed by material artifacts at `stitch/logical_stitched_analysis_shell.json`, `render/stitched_shell.glb`, and `reports/geometry_stitched_shell.json`.
- `meshStitchOrWeldProven=false`.
- `acceptedForCleanProposal=false`.
- `acceptedForCanonical=false`.

Current blocking evidence:

- 23 non-manifold edges and 29 non-manifold vertices.
- 8 duplicate faces.
- 3 boundary components rather than four proven semantic openings.
- Boundary graph contains branch vertices.
- Seam operation IDs include duplicates.
- Semantic opening assignment is not implemented.
- Stitched-shell binding coverage is incomplete.
- `selfIntersectionCheckStatus=not_run`.
- `tJunctionCheckStatus=not_run`.
- `inconsistentWindingCheckStatus=not_run`.
- `normalInversionCheckStatus=not_run`.
- `hiddenInternalComponentCheckStatus=not_run`.

## Files And Functions Involved

- `.gitignore`
- `engine/CMakeLists.txt`
- `engine/build/_deps/glfw-src`
- `engine/build/_deps/glm-src`
- `closy-forge/tests/unit/test_repository_hygiene.py`
- `closy-forge/src/closy_forge/proposals/geometry_stitched_shell.py`
- `closy-forge/src/closy_forge/pipeline/build_tshirt_demo.py`
- `closy-forge/src/closy_forge/validation/validator.py`
- `closy-forge/src/closy_forge/contracts/schema_registry.py`
- `closy-forge/docs/MASTER_BLUEPRINT_PROGRESS.md`
- `closy-forge/docs/blueprint_coverage.json`
- `closy-forge/tests/unit/test_blueprint_coverage.py`
- `closy-forge/tests/unit/test_geometry_proposal.py`
- `closy-forge/tests/corruption/test_corrupted_packages.py`

## Checks Completed After This Resume Update

- `python -m pytest tests/unit/test_repository_hygiene.py -q`
- `python -m ruff check tests/unit/test_repository_hygiene.py`
- `python -m ruff format tests/unit/test_repository_hygiene.py --check`
- `git ls-files --stage` no longer reports generated engine `_deps/*-src` gitlinks.
- `python -m pytest tests/unit/test_geometry_proposal.py -q`
- `python -m pytest tests/unit/test_blueprint_coverage.py -q`
- `python -m pytest tests/golden/test_golden_demo.py tests/unit/test_blueprint_coverage.py -q`
- `python -m pytest tests/corruption/test_corrupted_packages.py -q`
- `python -m ruff format src tests`
- `python -m ruff check src tests`
- `python -m mypy src`
- `python -m pytest -q`
- `python -m closy_forge schemas export --output schemas/v1`
- `python -m closy_forge schemas check --schema-dir schemas/v1 --json`
- deterministic temp-path `demo build-tshirt` produced digest `f84091eb6bdd3f9e42e40a7319580cbf24699f41b1e3b7b306a2a564087771e0` twice.
- `python -m closy_forge packages diff` reported the two temp packages identical, with 68 files on each side.
- `python -m closy_forge validate` passed with the single current package validation warning `self_collision_not_run`.
- `python -m closy_forge report` confirmed the same package digest and the rejected clean-acceptance state.
- GitHub Actions run `32658750731` before this resume record: full Forge matrix passed for the BP-46 closeout proof-invariant commit.

## Current Checks Not Yet Run After This Resume Update

- Remote CI for the repository gitlink hygiene checkpoint is pending until the hygiene and ledger commits are pushed.

## Next Exact Command

```powershell
cd E:\apps\Closy\closy-forge
.\.venv\Scripts\python.exe -m pytest tests\unit\test_repository_hygiene.py tests\unit\test_blueprint_coverage.py -q
```

## Next Safe Action

Commit and push the repository gitlink hygiene ledger correction, inspect remote CI to confirm the checkout annotations disappear, then implement the strict sanitized Forge failure-diagnostics exporter before BP-47 inspection artifacts.
