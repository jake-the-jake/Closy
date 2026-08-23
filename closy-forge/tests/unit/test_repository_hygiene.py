from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def test_generated_engine_dependency_sources_are_not_tracked_gitlinks() -> None:
    staged_files = _git("ls-files", "--stage", "--", "engine/build/_deps").splitlines()
    generated_gitlinks = [
        line for line in staged_files if line.startswith("160000 ") and "-src" in line
    ]

    assert generated_gitlinks == []


def test_generated_engine_build_tree_is_ignored() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "/engine/build/" in gitignore
