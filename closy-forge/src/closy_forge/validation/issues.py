from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Severity = Literal["info", "warning", "error", "fatal"]


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: Severity
    path: str
    message: str
    remediation: str
    entity_id: str | None = None

    def to_json(self) -> dict[str, object]:
        return asdict(self)
