from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "closy-forge/fixtures/solver_material_v1/frozen_guard_manifest.json"
SELF_PATH = "closy-forge/fixtures/solver_material_v1/frozen_guard_manifest.json"


def _git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def check_guard() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    unsigned_manifest = dict(manifest)
    observed_manifest_digest = str(unsigned_manifest.pop("manifestDigest", ""))
    expected_manifest_digest = hashlib.sha256(
        (json.dumps(unsigned_manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    frozen_head = str(manifest["frozenHead"])
    failures: list[str] = []
    if observed_manifest_digest != expected_manifest_digest:
        failures.append("guard_manifest_digest_invalid")
    for row in manifest["frozenFiles"]:
        path = str(row["path"])
        oid = _git("rev-parse", f"{frozen_head}:{path}").decode().strip()
        blob = _git("cat-file", "blob", oid)
        if oid != row["gitBlobOid"]:
            failures.append(f"blob_oid_changed:{path}")
        if hashlib.sha256(blob).hexdigest() != row["sha256"]:
            failures.append(f"sha256_changed:{path}")
        current_oid = _git("rev-parse", f"HEAD:{path}").decode().strip()
        if current_oid != oid:
            failures.append(f"frozen_path_changed:{path}")
    changed = _git("diff", "--name-only", f"{frozen_head}..HEAD").decode().splitlines()
    allowed = [str(value) for value in manifest["allowedAppendOnlyPrefixes"]] + [SELF_PATH]
    unauthorized = [
        path for path in changed if not any(path.startswith(prefix) for prefix in allowed)
    ]
    failures.extend(f"append_only_path_not_allowed:{path}" for path in unauthorized)
    receipt = {
        "guardVersion": manifest["guardVersion"],
        "manifestDigest": observed_manifest_digest,
        "frozenHead": frozen_head,
        "checkedFileCount": len(manifest["frozenFiles"]),
        "appendOnlyChangedFileCount": len(changed),
        "failureCount": len(failures),
        "failures": failures,
        "status": "pass" if not failures else "integrity_error",
    }
    if failures:
        raise SystemExit(json.dumps(receipt, sort_keys=True))
    return receipt


if __name__ == "__main__":
    print(json.dumps(check_guard(), sort_keys=True))
