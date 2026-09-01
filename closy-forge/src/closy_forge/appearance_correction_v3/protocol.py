from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file

PROTOCOL_PATH = Path("fixtures/d0_texture_rerender_correction_v3/protocol_lock.json")
PROTOCOL_SHA256 = "85c3082f2efcce5f7dfab0d13af0ebe85a8fd0e9e8f621e5b48e9ba8b95d218b"


def load_correction_protocol(root: Path) -> dict[str, Any]:
    path = root / PROTOCOL_PATH
    if sha256_file(path) != PROTOCOL_SHA256:
        raise ValueError("d0_appearance_protocol_hash_mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("d0_appearance_protocol_invalid")
    _validate_protocol(payload)
    return payload


def _validate_protocol(protocol: Mapping[str, Any]) -> None:
    if protocol.get("lockId") != (
        "closy.d0_texture_rerender_correction.known_target_regression.v3"
    ):
        raise ValueError("d0_appearance_protocol_id_invalid")
    strategy = _mapping(protocol.get("strategy"))
    if strategy.get("maximumAppearanceStrategies") != 1:
        raise ValueError("d0_appearance_strategy_budget_invalid")
    if strategy.get("maximumKnownTargetTrials") != 1:
        raise ValueError("d0_appearance_trial_budget_invalid")
    if strategy.get("geometryOrPhysicsChangesAllowed") is not False:
        raise ValueError("d0_appearance_geometry_change_permitted")
    allowed = _mapping(protocol.get("sourceClosure")).get("allowedViews")
    if not isinstance(allowed, list) or len(allowed) != 2:
        raise ValueError("d0_appearance_source_closure_invalid")
    if {str(_mapping(item).get("role", "")) for item in allowed} != {"front", "rear"}:
        raise ValueError("d0_appearance_source_roles_invalid")
    target = _mapping(protocol.get("knownEvaluatorTarget"))
    if target.get("accessStateBeforePredictionFreeze") != "not_mounted":
        raise ValueError("d0_appearance_evaluator_premounted")
    outcome = _mapping(protocol.get("outcomePolicy"))
    if outcome.get("mayPromoteD0Rp07") is not False:
        raise ValueError("d0_appearance_known_target_promotes_d0rp07")
    if outcome.get("mayPromoteResearchPrototype") is not False:
        raise ValueError("d0_appearance_known_target_promotes_research_prototype")
    provenance = _mapping(protocol.get("sourceToTexelProvenanceContract"))
    if provenance.get("generatedTexelsExcludedFromSourceFidelity") is not True:
        raise ValueError("d0_appearance_generated_fidelity_inclusion")
    if provenance.get("logoObservedPixelsMayBeOverwritten") is not False:
        raise ValueError("d0_appearance_logo_overwrite_permitted")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
