from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from closy_forge.package_io.managed_output import (
    MARKER_NAME,
    ManagedOutputError,
    create_managed_staging,
    publish_managed_staging,
    validate_output_target,
)

PURPOSE = "test-artifact"


def _publish(root: Path, target: Path, text: str, *, force: bool) -> None:
    staging = create_managed_staging(target, allowed_root=root, purpose=PURPOSE)
    (staging / "payload.txt").write_text(text, encoding="utf-8")
    publish_managed_staging(
        staging,
        target,
        allowed_root=root,
        purpose=PURPOSE,
        force=force,
    )


def test_managed_output_publishes_and_replaces_only_marked_direct_child(tmp_path: Path) -> None:
    root = tmp_path / "allowed"
    target = root / "result"

    _publish(root, target, "old", force=False)
    _publish(root, target, "new", force=True)

    assert (target / "payload.txt").read_text(encoding="utf-8") == "new"
    marker = json.loads((target / MARKER_NAME).read_text(encoding="utf-8"))
    assert marker["markerVersion"] == "closy.forge_owned_output.v1"
    assert marker["purpose"] == PURPOSE
    assert marker["kind"] == "published"


def test_managed_output_rejects_unmarked_force_target(tmp_path: Path) -> None:
    root = tmp_path / "allowed"
    target = root / "result"
    target.mkdir(parents=True)
    (target / "user.txt").write_text("preserve", encoding="utf-8")
    staging = create_managed_staging(target, allowed_root=root, purpose=PURPOSE)

    with pytest.raises(ManagedOutputError, match="managed_output_marker_missing"):
        publish_managed_staging(
            staging,
            target,
            allowed_root=root,
            purpose=PURPOSE,
            force=True,
        )
    assert (target / "user.txt").read_text(encoding="utf-8") == "preserve"


def test_managed_output_rejects_broad_nested_and_protected_paths(tmp_path: Path) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    with pytest.raises(ManagedOutputError, match="direct_child"):
        validate_output_target(root / "nested" / "result", allowed_root=root, purpose=PURPOSE)
    with pytest.raises(ManagedOutputError, match="protected_output_target_rejected"):
        validate_output_target(Path.home() / "result", allowed_root=Path.home(), purpose=PURPOSE)
    with pytest.raises(ManagedOutputError, match="protected_output_target_rejected"):
        validate_output_target(
            Path(Path.cwd().anchor) / "result",
            allowed_root=Path(Path.cwd().anchor),
            purpose=PURPOSE,
        )


def test_managed_output_rejects_stale_and_mismatched_markers(tmp_path: Path) -> None:
    root = tmp_path / "allowed"
    target = root / "result"
    _publish(root, target, "old", force=False)
    marker_path = target / MARKER_NAME
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["markerVersion"] = "stale.v0"
    marker_path.write_text(json.dumps(marker), encoding="utf-8")

    staging = create_managed_staging(target, allowed_root=root, purpose=PURPOSE)
    with pytest.raises(ManagedOutputError, match="marker_version_mismatch"):
        publish_managed_staging(
            staging,
            target,
            allowed_root=root,
            purpose=PURPOSE,
            force=True,
        )

    marker["markerVersion"] = "closy.forge_owned_output.v1"
    marker["purpose"] = "other-purpose"
    marker_path.write_text(json.dumps(marker), encoding="utf-8")
    with pytest.raises(ManagedOutputError, match="purpose_mismatch"):
        publish_managed_staging(
            staging,
            target,
            allowed_root=root,
            purpose=PURPOSE,
            force=True,
        )


def test_managed_output_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "allowed"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "result"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable on this host")

    with pytest.raises(ManagedOutputError, match="output_symlink_rejected"):
        create_managed_staging(link, allowed_root=root, purpose=PURPOSE)


def test_interrupted_publish_restores_last_good_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "allowed"
    target = root / "result"
    _publish(root, target, "old", force=False)
    staging = create_managed_staging(target, allowed_root=root, purpose=PURPOSE)
    (staging / "payload.txt").write_text("new", encoding="utf-8")
    real_replace = os.replace
    failed = False

    def interrupted_replace(source: str | bytes | Path, destination: str | bytes | Path) -> None:
        nonlocal failed
        if Path(source) == staging and Path(destination) == target and not failed:
            failed = True
            raise OSError("injected publication interruption")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", interrupted_replace)
    with pytest.raises(OSError, match="injected publication interruption"):
        publish_managed_staging(
            staging,
            target,
            allowed_root=root,
            purpose=PURPOSE,
            force=True,
        )

    assert (target / "payload.txt").read_text(encoding="utf-8") == "old"
    marker = json.loads((target / MARKER_NAME).read_text(encoding="utf-8"))
    assert marker["kind"] == "published"
