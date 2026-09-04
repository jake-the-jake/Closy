from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .common import digest_file, digest_value, write_json
from .evaluation import copy_first_build, evaluate_locked_manual_provider_corpus, write_result
from .independent_checker import check_publication
from .source_freeze import verify_source_freeze


def publish_manual_provider_c3_v1(repository: Path, publication_root: Path) -> dict[str, Any]:
    if publication_root.exists():
        raise ValueError("manual_provider_publication_root_must_not_exist")
    forge_root = repository / "closy-forge"
    fixture_root = forge_root / "fixtures" / "manual_provider_c3_v1"
    source_freeze_path = fixture_root / "source_freeze.json"
    from .common import read_json

    verify_source_freeze(repository, read_json(source_freeze_path))
    with tempfile.TemporaryDirectory(prefix="closy-mpc3-v1-") as temporary:
        temporary_root = Path(temporary)
        build_a = temporary_root / "build-a"
        build_b = temporary_root / "build-b"
        result, _ = evaluate_locked_manual_provider_corpus(
            fixture_root,
            build_a,
            build_b,
            source_freeze_path=source_freeze_path,
        )
        publication_root.mkdir(parents=True)
        copy_first_build(build_a, publication_root / "packages")
        result_path = publication_root / "result.json"
        write_result(result_path, result)
        checker = check_publication(publication_root, result_path)
        write_json(publication_root / "independent_checker.json", checker)
    inventory = [
        {
            "path": path.relative_to(publication_root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": digest_file(path),
        }
        for path in sorted(publication_root.rglob("*"))
        if path.is_file() and path.name != "publication_manifest.json"
    ]
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "publicationVersion": "closy.manual_provider_c3_v1.publication.v1",
        "resultDigest": result["resultDigest"],
        "checkerDigest": checker["checkerDigest"],
        "inventory": inventory,
        "inventoryDigest": digest_value(inventory),
        "benchmarkRunCount": 1,
        "status": "published",
    }
    manifest["publicationDigest"] = digest_value(manifest)
    write_json(publication_root / "publication_manifest.json", manifest)
    return manifest
