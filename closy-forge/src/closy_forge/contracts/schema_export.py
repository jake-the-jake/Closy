from __future__ import annotations

from pathlib import Path

from closy_forge.contracts.schema_registry import schema_registry
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json


def export_schemas(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, schema in sorted(schema_registry().items()):
        path = output_dir / filename
        write_canonical_json(path, schema)
        written.append(path)
    return written


def checked_in_schemas_fresh(schema_dir: Path) -> tuple[bool, list[str]]:
    issues: list[str] = []
    registry = schema_registry()
    for filename, schema in sorted(registry.items()):
        path = schema_dir / filename
        if not path.exists():
            issues.append(f"missing:{filename}")
            continue
        if path.read_text(encoding="utf-8") != canonical_dumps(schema):
            issues.append(f"stale:{filename}")
    extra = sorted(
        path.name for path in schema_dir.glob("*.schema.json") if path.name not in registry
    )
    issues.extend(f"extra:{name}" for name in extra)
    return not issues, issues
