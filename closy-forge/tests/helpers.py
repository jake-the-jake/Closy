from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.pipeline.build_long_sleeved_demo import build_demo_long_sleeved_package
from closy_forge.pipeline.build_simple_skirt_demo import build_demo_simple_skirt_package
from closy_forge.pipeline.build_simple_trousers_demo import build_demo_simple_trousers_package
from closy_forge.pipeline.build_sleeveless_demo import build_demo_sleeveless_package
from closy_forge.pipeline.build_tshirt_demo import build_demo_tshirt_package

_DEMO_CACHE: Path | None = None
_SLEEVELESS_CACHE: Path | None = None
_LONG_SLEEVED_CACHE: Path | None = None
_SIMPLE_SKIRT_CACHE: Path | None = None
_SIMPLE_TROUSERS_CACHE: Path | None = None


def build_demo(tmp_path: Path, name: str = "demo_tshirt.closygarment") -> Path:
    output = tmp_path / name
    return clone_package(_cached_demo_package(), output)


def build_sleeveless(tmp_path: Path, name: str = "demo_sleeveless.closygarment") -> Path:
    output = tmp_path / name
    return clone_package(_cached_sleeveless_package(), output)


def build_long_sleeved(tmp_path: Path, name: str = "demo_long_sleeved.closygarment") -> Path:
    output = tmp_path / name
    return clone_package(_cached_long_sleeved_package(), output)


def build_simple_skirt(tmp_path: Path, name: str = "demo_simple_skirt.closygarment") -> Path:
    output = tmp_path / name
    return clone_package(_cached_simple_skirt_package(), output)


def build_simple_trousers(tmp_path: Path, name: str = "demo_simple_trousers.closygarment") -> Path:
    output = tmp_path / name
    return clone_package(_cached_simple_trousers_package(), output)


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


def _cached_demo_package() -> Path:
    global _DEMO_CACHE
    if _DEMO_CACHE is None:
        cache_root = Path(tempfile.mkdtemp(prefix="closy_forge_pytest_demo_"))
        package = cache_root / "demo_tshirt.closygarment"
        build_demo_tshirt_package(package, force=True)
        _DEMO_CACHE = package
    return _DEMO_CACHE


def _cached_sleeveless_package() -> Path:
    global _SLEEVELESS_CACHE
    if _SLEEVELESS_CACHE is None:
        cache_root = Path(tempfile.mkdtemp(prefix="closy_forge_pytest_sleeveless_"))
        package = cache_root / "demo_sleeveless.closygarment"
        build_demo_sleeveless_package(package, force=True)
        _SLEEVELESS_CACHE = package
    return _SLEEVELESS_CACHE


def _cached_long_sleeved_package() -> Path:
    global _LONG_SLEEVED_CACHE
    if _LONG_SLEEVED_CACHE is None:
        cache_root = Path(tempfile.mkdtemp(prefix="closy_forge_pytest_long_sleeved_"))
        package = cache_root / "demo_long_sleeved.closygarment"
        build_demo_long_sleeved_package(package, force=True)
        _LONG_SLEEVED_CACHE = package
    return _LONG_SLEEVED_CACHE


def _cached_simple_skirt_package() -> Path:
    global _SIMPLE_SKIRT_CACHE
    if _SIMPLE_SKIRT_CACHE is None:
        cache_root = Path(tempfile.mkdtemp(prefix="closy_forge_pytest_simple_skirt_"))
        package = cache_root / "demo_simple_skirt.closygarment"
        build_demo_simple_skirt_package(package, force=True)
        _SIMPLE_SKIRT_CACHE = package
    return _SIMPLE_SKIRT_CACHE


def _cached_simple_trousers_package() -> Path:
    global _SIMPLE_TROUSERS_CACHE
    if _SIMPLE_TROUSERS_CACHE is None:
        cache_root = Path(tempfile.mkdtemp(prefix="closy_forge_pytest_simple_trousers_"))
        package = cache_root / "demo_simple_trousers.closygarment"
        build_demo_simple_trousers_package(package, force=True)
        _SIMPLE_TROUSERS_CACHE = package
    return _SIMPLE_TROUSERS_CACHE
