from __future__ import annotations

from pathlib import Path

from closy_forge.ci import test_shards as test_shard_module
from closy_forge.ci.test_shards import (
    TEST_SHARD_NAMES,
    assign_test_shards,
    discover_sharded_tests,
    main,
    validate_test_shards,
)

FORGE_ROOT = Path(__file__).resolve().parents[2]


def test_test_shards_cover_every_unit_and_corruption_file_once() -> None:
    shards = assign_test_shards(FORGE_ROOT)
    assigned = [path for name in TEST_SHARD_NAMES for path in shards[name]]

    assert validate_test_shards(FORGE_ROOT) == []
    assert len(assigned) == len(set(assigned))
    assert set(assigned) == set(discover_sharded_tests(FORGE_ROOT))


def test_integration_shards_cover_every_integration_and_golden_file_once() -> None:
    shards = assign_test_shards(FORGE_ROOT, "integration")
    assigned = [path for paths in shards.values() for path in paths]

    assert validate_test_shards(FORGE_ROOT, "integration") == []
    assert len(assigned) == len(set(assigned))
    assert set(assigned) == set(discover_sharded_tests(FORGE_ROOT, "integration"))


def test_test_shard_list_mode_is_bounded_and_does_not_run_pytest(capsys) -> None:
    shards = assign_test_shards(FORGE_ROOT)

    assert main(["--group", "shard-1", "--list"]) == 0
    assert capsys.readouterr().out.splitlines() == list(shards["shard-1"])


def test_invalid_integration_shard_fails_closed(capsys) -> None:
    assert main(["--suite", "integration", "--group", "shard-3", "--list"]) == 2
    assert "invalid shard for integration" in capsys.readouterr().err


def test_nested_test_is_recursively_discovered_and_assigned_once(tmp_path: Path) -> None:
    nested = tmp_path / "tests" / "unit" / "nested" / "test_new_guard.py"
    nested.parent.mkdir(parents=True)
    nested.write_text("def test_guard(): pass\n", encoding="utf-8")
    for directory in (tmp_path / "tests" / "corruption",):
        directory.mkdir(parents=True)
    discovered = discover_sharded_tests(tmp_path)
    assigned = [path for paths in assign_test_shards(tmp_path).values() for path in paths]

    assert discovered == ("tests/unit/nested/test_new_guard.py",)
    assert assigned.count(discovered[0]) == 1


def test_inventory_digest_is_stable_and_changes_with_recursive_inventory(tmp_path: Path) -> None:
    unit = tmp_path / "tests" / "unit"
    corruption = tmp_path / "tests" / "corruption"
    unit.mkdir(parents=True)
    corruption.mkdir(parents=True)
    (unit / "test_a.py").write_text("", encoding="utf-8")
    first = test_shard_module.test_inventory_digest(tmp_path)
    assert first == test_shard_module.test_inventory_digest(tmp_path)

    nested = corruption / "nested" / "test_b.py"
    nested.parent.mkdir()
    nested.write_text("", encoding="utf-8")

    assert test_shard_module.test_inventory_digest(tmp_path) != first
