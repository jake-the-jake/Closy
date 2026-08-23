from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.pipeline.build_tshirt_demo import build_demo_tshirt_package


def build_demo(tmp_path: Path, name: str = "demo_tshirt.closygarment") -> Path:
    output = tmp_path / name
    build_demo_tshirt_package(output, force=True)
    return output


def clone_package(package_dir: Path, target: Path) -> Path:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(package_dir, target)
    return target


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    write_canonical_json(path, data)


def issue_codes(report: dict[str, Any]) -> set[str]:
    return {str(issue["code"]) for issue in report["issues"]}
