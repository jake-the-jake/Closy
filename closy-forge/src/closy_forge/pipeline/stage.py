from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StageRecord:
    stage_id: str
    version: str
    status: str
    input_fingerprint: str
    output_hashes: dict[str, str]
    warnings: list[str]
    recoverability: str = "rebuild_from_inputs"
