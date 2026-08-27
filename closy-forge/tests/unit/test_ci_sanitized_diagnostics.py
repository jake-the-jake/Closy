from __future__ import annotations

import json
import os
from pathlib import Path

from closy_forge.ci import export_sanitized_ci_diagnostics
from closy_forge.cli.main import EXIT_SUCCESS, main
from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.managed_output import MARKER_NAME


def test_sanitized_ci_diagnostics_writes_allowlisted_summaries(tmp_path: Path) -> None:
    source = tmp_path / "raw-ci"
    package = source / "demo_a.closygarment"
    reports = package / "reports"
    render = package / "render"
    reports.mkdir(parents=True)
    render.mkdir()
    output = tmp_path / "safe-diagnostics"

    write_canonical_json(
        package / "manifest.json",
        {
            "schemaVersion": 1,
            "garmentId": "garment.demo_tshirt.reference_v1",
            "canonicalPackageDigest": "a" * 64,
            "inventory": [
                {
                    "path": "render/stitched_shell.glb",
                    "role": "render-preview",
                    "sha256": "b" * 64,
                    "canonical": False,
                }
            ],
        },
    )
    write_canonical_json(
        reports / "package_validation.json",
        {
            "schemaVersion": 1,
            "status": "passed",
            "counts": {"error": 0, "fatal": 0, "info": 0, "warning": 1},
            "issues": [{"code": "self_collision_not_run", "severity": "warning"}],
        },
    )
    (render / "stitched_shell.glb").write_bytes(b"glTF forbidden model bytes")
    (source / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n forbidden image bytes")
    (source / "renamed-image.txt").write_bytes(b"\x89PNG\r\n\x1a\n renamed image bytes")
    (source / "embedded.txt").write_text("payload=iVBORw0KGgoAAAANS", encoding="utf-8")
    (source / "absolute.txt").write_text(
        r"C:\Users\Alice\Pictures\private-face.png",
        encoding="utf-8",
    )
    (source / "unc.txt").write_text(
        r"\\nas01\homes\Alice\captures\front.png",
        encoding="utf-8",
    )
    (source / "mixed.txt").write_text(
        "images/../private_capture.png",
        encoding="utf-8",
    )
    raw_token = "AbCDefGhIJklMNopQRstUVwxYZ0123456789abcdEFGHijklMNOP"
    (source / "opaque.txt").write_text(raw_token, encoding="utf-8")
    (source / "plain.txt").write_text("plain diagnostic text", encoding="utf-8")
    symlink_created = False
    hardlink_created = False
    try:
        (source / "symlink.txt").symlink_to(source / "absolute.txt")
        symlink_created = True
    except OSError:
        symlink_created = False
    try:
        os.link(source / "plain.txt", source / "hardlink.txt")
        hardlink_created = True
    except OSError:
        hardlink_created = False

    summary = export_sanitized_ci_diagnostics(
        source,
        output,
        allowed_output_root=tmp_path,
    )

    assert summary["outputPolicy"]["copiesSourceBytes"] is False
    assert sorted(path.name for path in output.iterdir()) == [
        MARKER_NAME,
        "package_inventory.json",
        "rejections.json",
        "summary.json",
        "validation_summary.json",
    ]
    combined_output = "\n".join(path.read_text(encoding="utf-8") for path in output.iterdir())
    assert str(tmp_path) not in combined_output
    assert "Alice" not in combined_output
    assert raw_token not in combined_output
    assert "iVBORw0KGgo" not in combined_output
    assert "glTF forbidden model bytes" not in combined_output

    rejections = json.loads((output / "rejections.json").read_text(encoding="utf-8"))
    assert rejections["countsByCode"]["forbidden_extension_rejected"] >= 2
    assert rejections["countsByCode"]["forbidden_magic_bytes_rejected"] >= 1
    assert rejections["countsByCode"]["embedded_capture_payload_rejected"] >= 1
    assert rejections["countsByCode"]["absolute_path_text_rejected"] >= 1
    assert rejections["countsByCode"]["path_traversal_text_rejected"] >= 1
    assert rejections["countsByCode"]["secret_like_text_rejected"] >= 1
    if symlink_created:
        assert rejections["countsByCode"]["symlink_rejected"] >= 1
    if hardlink_created:
        assert rejections["countsByCode"]["hardlink_rejected"] >= 1

    inventory = json.loads((output / "package_inventory.json").read_text(encoding="utf-8"))
    assert inventory["packages"][0]["inventoryCount"] == 1
    assert inventory["packages"][0]["canonicalEntryCount"] == 0
    assert inventory["packages"][0]["roleCounts"] == {"render-preview": 1}
    assert inventory["packages"][0]["hashesIncluded"] is False
    assert inventory["packages"][0]["pathsIncluded"] is False
    assert "a" * 64 not in combined_output
    assert "b" * 64 not in combined_output
    assert "demo_a.closygarment" not in combined_output


def test_ci_diagnostics_cli_uses_safe_output_directory(tmp_path: Path) -> None:
    source = tmp_path / "raw-ci"
    source.mkdir()
    output = tmp_path / "safe-diagnostics"

    exit_code = main(
        [
            "ci",
            "diagnostics",
            "--source-dir",
            str(source),
            "--output",
            str(output),
            "--output-root",
            str(tmp_path),
        ]
    )

    assert exit_code == EXIT_SUCCESS
    assert sorted(path.name for path in output.iterdir()) == [
        MARKER_NAME,
        "package_inventory.json",
        "rejections.json",
        "summary.json",
        "validation_summary.json",
    ]
