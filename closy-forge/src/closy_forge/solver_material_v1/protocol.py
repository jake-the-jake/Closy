from __future__ import annotations

from pathlib import Path
from typing import Any

from closy_forge.solver_material_v1.common import digest, read_json

PROTOCOL_VERSION = "closy.solver_material_engineering.protocol.v1"
FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "fixtures"
    / "solver_material_v1"
    / "acceptance_protocol.json"
)


def load_protocol() -> dict[str, Any]:
    protocol = read_json(FIXTURE)
    if protocol.get("protocolVersion") != PROTOCOL_VERSION:
        raise ValueError("solver_material_protocol_version_invalid")
    expected = str(protocol.pop("protocolDigest", ""))
    actual = digest(protocol)
    protocol["protocolDigest"] = expected
    if expected != actual:
        raise ValueError("solver_material_protocol_digest_invalid")
    return protocol
