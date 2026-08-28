from __future__ import annotations

from pathlib import Path

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


def test_test_shard_list_mode_is_bounded_and_does_not_run_pytest(capsys) -> None:
    shards = assign_test_shards(FORGE_ROOT)

    assert main(["--group", "shard-1", "--list"]) == 0
    assert capsys.readouterr().out.splitlines() == list(shards["shard-1"])
