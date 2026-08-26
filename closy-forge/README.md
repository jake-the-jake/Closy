# Closy Forge

Closy Forge is the isolated Python sidecar for deterministic avatar-and-garment package construction. It is not imported by the Expo app, does not run on phones, and does not depend on ZeroOne, GPU tooling, AI providers, user imagery, or external services.

The current deterministic fixture builds one authored T-shirt package with synthetic metadata-only capture records, analytic mask/landmark observations, an empty correction ledger, deterministic T-shirt parameter fitting, texture/PBR identity evidence, a rejected null visual-geometry proposal boundary, analytic rest state, CPU reference settle state, conventional GLBs, and sim-to-render binding:

```bash
python -m closy_forge demo build-tshirt --output generated/garments/demo_tshirt.closygarment
python -m closy_forge validate generated/garments/demo_tshirt.closygarment
python -m closy_forge report generated/garments/demo_tshirt.closygarment
python -m closy_forge capture build-synthetic --output generated/capture/synthetic_tshirt --force
```

The BP-49 raster path is fixture-only and keeps private registry records
separate from portable reports:

```bash
python -m closy_forge capture ingest-raster-fixture --manifest fixtures/raster_manifest.json --input-root fixtures --private-registry generated/private/raster --portable-output generated/capture/raster --force
python -m closy_forge capture delete-raster-fixture --private-registry generated/private/raster --tombstone generated/private/raster_tombstone.json --force
```

After installation, the console script is equivalent:

```bash
closy-forge demo build-tshirt --output generated/garments/demo_tshirt.closygarment
closy-forge validate generated/garments/demo_tshirt.closygarment
closy-forge report generated/garments/demo_tshirt.closygarment --json
```

## Setup

Windows PowerShell:

```powershell
cd closy-forge
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[dev] -c requirements-dev.lock
```

macOS/Linux:

```bash
cd closy-forge
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]' -c requirements-dev.lock
```

## Verification

```bash
python -m ruff check .
python -m mypy src
python -m pytest
python -m closy_forge schemas check --schema-dir schemas/v1
python -m closy_forge demo build-tshirt --output ../generated/garments/demo_tshirt.closygarment --force
python -m closy_forge validate ../generated/garments/demo_tshirt.closygarment
python -m closy_forge report ../generated/garments/demo_tshirt.closygarment
```

CLI exit codes:

- `0` success
- `2` command/argument error
- `3` package validation failure
- `4` deterministic build failure
- `5` unsafe path or integrity failure

## Boundary

Forge owns versioned `.closygarment` package contracts, deterministic fixture generation, package validation, reports, and future headless reconstruction stages. The Expo app, C++ prototype engine, Supabase storage, and ZeroOne bridges remain separate consumers/neighbours.

See:

- `docs/architecture.md` for the full boundary.
- `docs/adr-0001-coordinate-convention.md` for the Forge coordinate ADR.
- `docs/package-contract-v1.md` for the package tree and manifest rules.
- `docs/tshirt-pattern-v1.md` for the deterministic T-shirt pattern contract.
- `docs/capture-records-v1.md` for synthetic source records, capture quality scoring, visual observations and correction records.
- `docs/raster-ingestion-v1.md` for BP-49 local synthetic PNG/JPEG fixture ingestion, privacy separation and deletion tombstones.
- `docs/texture-identity-v1.md` for synthetic texture identity and mobile-safe PBR evidence.
- `docs/geometry-proposal-contract-v1.md` for the raw/clean visual-geometry proposal boundary.
- `docs/cloth-settle-reference-v1.md` for the CPU reference settle backend.
- `docs/material-physics-d0.md` for Phase 7 descriptors, selection, calibration and motion evidence.
- `docs/MASTER_BLUEPRINT_PROGRESS.md` for the evidence ledger across the master blueprint.
- `docs/future-handoff.md` for future reconstruction and ZeroOne boundaries.
- `../docs/closy-garment-package-v1.md` for the repository-level package overview.
