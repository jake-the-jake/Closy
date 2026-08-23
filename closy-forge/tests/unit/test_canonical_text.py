from __future__ import annotations

from closy_forge.package_io.canonical_json import canonical_text_bytes, write_canonical_text


def test_canonical_text_bytes_are_utf8_lf_with_single_final_newline() -> None:
    assert canonical_text_bytes("alpha\r\nbeta\rgamma\n\n") == b"alpha\nbeta\ngamma\n"


def test_write_canonical_text_never_uses_platform_newline_translation(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "nested" / "artifact.txt"
    write_canonical_text(path, "line one\r\nline two")
    assert path.read_bytes() == b"line one\nline two\n"
