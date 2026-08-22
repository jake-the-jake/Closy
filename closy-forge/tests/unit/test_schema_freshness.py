from __future__ import annotations

from pathlib import Path

from closy_forge.contracts.schema_export import checked_in_schemas_fresh
from closy_forge.contracts.schema_registry import schema_registry
from closy_forge.package_io.canonical_json import read_json


def test_checked_in_schemas_match_registry() -> None:
    schema_dir = Path(__file__).resolve().parents[2] / "schemas" / "v1"
    fresh, issues = checked_in_schemas_fresh(schema_dir)
    assert fresh, issues


def test_schema_files_are_parseable_and_versioned() -> None:
    schema_dir = Path(__file__).resolve().parents[2] / "schemas" / "v1"
    assert len(list(schema_dir.glob("*.schema.json"))) == len(schema_registry())
    for path in schema_dir.glob("*.schema.json"):
        schema = read_json(path)
        assert schema["properties"]["schemaVersion"]["const"] == 1


def test_core_schemas_forbid_unknown_root_fields() -> None:
    for name, schema in schema_registry().items():
        assert schema["additionalProperties"] is False, name
