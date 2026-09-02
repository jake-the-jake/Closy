from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from closy_forge.truth_authority_integrity_v3.output_collector import (
    OutputCollectionError,
    collect_declared_outputs,
)


def _assert_quarantined(output: Path) -> None:
    assert output.is_dir()
    assert not any(output.iterdir())


def test_undeclared_and_hardlinked_outputs_are_quarantined(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (output / "undeclared.txt").write_text("sensitive", encoding="utf-8")
    with pytest.raises(OutputCollectionError, match="output_name_or_depth_forbidden"):
        collect_declared_outputs(output)
    _assert_quarantined(output)

    original = output / "probe.json"
    original.write_text("{}", encoding="utf-8")
    os.link(original, output / "prediction.json")
    with pytest.raises(OutputCollectionError, match="output_hardlink_forbidden"):
        collect_declared_outputs(output)
    _assert_quarantined(output)


def test_post_lstat_replacement_race_is_quarantined(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (output / "probe.json").write_text("before", encoding="utf-8")

    def replace(path: Path) -> None:
        replacement = path.with_suffix(".replacement")
        replacement.write_text("after", encoding="utf-8")
        os.replace(replacement, path)

    with pytest.raises(OutputCollectionError, match="output_inode_or_device_changed"):
        collect_declared_outputs(output, after_lstat=replace)
    _assert_quarantined(output)


@pytest.mark.skipif(os.name == "nt", reason="POSIX file types are not constructible on Windows")
def test_symlink_fifo_and_socket_outputs_are_quarantined(tmp_path: Path) -> None:
    constructors = (
        lambda path: path.symlink_to(tmp_path / "outside"),
        os.mkfifo,
        _unix_socket,
    )
    (tmp_path / "outside").write_text("sensitive", encoding="utf-8")
    for ordinal, constructor in enumerate(constructors):
        output = tmp_path / f"output-{ordinal}"
        output.mkdir()
        constructor(output / "probe.json")
        with pytest.raises(OutputCollectionError):
            collect_declared_outputs(output)
        _assert_quarantined(output)


def _unix_socket(path: Path) -> None:
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(path))
    finally:
        server.close()
