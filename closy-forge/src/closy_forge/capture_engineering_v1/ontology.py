from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, TypedDict, cast

from .common import canonical_digest

SceneCondition = Literal["flat", "hung", "worn", "unknown"]
AcquisitionPattern = Literal["single_image", "guided_multi_image", "guided_video"]
ViewRole = Literal["front", "rear", "side", "three-quarter", "detail"]
SubjectCondition = Literal["no_body", "fixed_synthetic_avatar", "future_authorized_person"]
EvidenceTier = Literal[
    "public_project_fixture", "future_licensed_public", "future_private_authorized"
]
PrimaryMode = Literal["A", "B", "C", "D", "E"]

SCENE_CONDITIONS = frozenset({"flat", "hung", "worn", "unknown"})
ACQUISITION_PATTERNS = frozenset({"single_image", "guided_multi_image", "guided_video"})
VIEW_ROLES = frozenset({"front", "rear", "side", "three-quarter", "detail"})
SUBJECT_CONDITIONS = frozenset({"no_body", "fixed_synthetic_avatar", "future_authorized_person"})
EVIDENCE_TIERS = frozenset(
    {"public_project_fixture", "future_licensed_public", "future_private_authorized"}
)
PRIMARY_MODES = frozenset({"A", "B", "C", "D", "E"})


class SessionFacets(TypedDict):
    sceneCondition: SceneCondition
    acquisitionPattern: AcquisitionPattern
    subjectCondition: SubjectCondition
    evidenceTier: EvidenceTier


class CaptureSession(TypedDict):
    schemaVersion: int
    sessionVersion: str
    opaqueSessionId: str
    identityGroupId: str
    primaryMode: PrimaryMode
    facets: SessionFacets
    viewRoles: list[ViewRole]
    sourceIds: list[str]
    corrections: list[dict[str, Any]]
    legacyModeC: dict[str, Any] | None
    sessionDigest: str


SESSION_VERSION = "closy.capture_session.composable.v1"


def build_session(
    *,
    opaque_session_id: str,
    identity_group_id: str,
    primary_mode: PrimaryMode,
    scene_condition: SceneCondition,
    acquisition_pattern: AcquisitionPattern,
    subject_condition: SubjectCondition,
    evidence_tier: EvidenceTier,
    view_roles: Sequence[ViewRole],
    source_ids: Sequence[str],
    corrections: Sequence[Mapping[str, Any]] = (),
    legacy_mode_c: Mapping[str, Any] | None = None,
) -> CaptureSession:
    session: CaptureSession = {
        "schemaVersion": 1,
        "sessionVersion": SESSION_VERSION,
        "opaqueSessionId": opaque_session_id,
        "identityGroupId": identity_group_id,
        "primaryMode": primary_mode,
        "facets": {
            "sceneCondition": scene_condition,
            "acquisitionPattern": acquisition_pattern,
            "subjectCondition": subject_condition,
            "evidenceTier": evidence_tier,
        },
        "viewRoles": list(view_roles),
        "sourceIds": list(source_ids),
        "corrections": [dict(item) for item in corrections],
        "legacyModeC": dict(legacy_mode_c) if legacy_mode_c is not None else None,
        "sessionDigest": "",
    }
    issues = validate_session(session)
    if issues:
        raise ValueError("invalid_capture_session:" + ";".join(issues))
    session["sessionDigest"] = canonical_digest(cast(dict[str, Any], session), "sessionDigest")
    return session


def migrate_legacy_mode_c(record: Mapping[str, Any]) -> CaptureSession:
    """Read the Phase-2 multi-view record without preserving divergent facet fields."""

    capture = _mapping(record.get("captureSession"))
    views = _sequence(record.get("views"))
    roles = [_legacy_role(_mapping(view).get("label")) for view in views]
    if len(roles) < 2:
        raise ValueError("legacy_mode_c_requires_multiple_views")
    record_id = str(record.get("recordId", "legacy-mode-c"))
    return build_session(
        opaque_session_id=f"migrated.{_safe_token(record_id)}",
        identity_group_id=f"legacy-group.{_safe_token(str(capture.get('sessionId', record_id)))}",
        primary_mode="C",
        scene_condition="unknown",
        acquisition_pattern="guided_multi_image",
        subject_condition=(
            "fixed_synthetic_avatar"
            if str(record.get("recordType", "")).startswith("synthetic")
            else "future_authorized_person"
        ),
        evidence_tier=(
            "public_project_fixture"
            if str(record.get("recordType", "")).startswith("synthetic")
            else "future_private_authorized"
        ),
        view_roles=roles,
        source_ids=[f"legacy-source.{index:02d}" for index in range(len(roles))],
        legacy_mode_c={
            "recordVersion": str(record.get("recordVersion", "unknown")),
            "recordId": record_id,
            "viewCount": len(roles),
            "backwardReadOnly": True,
            "duplicateFacetFieldsPersisted": False,
        },
    )


def validate_session(session: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    facets = _mapping(session.get("facets"))
    roles = _sequence(session.get("viewRoles"))
    sources = _sequence(session.get("sourceIds"))
    if session.get("sessionVersion") != SESSION_VERSION:
        issues.append("session_version_invalid")
    if session.get("primaryMode") not in PRIMARY_MODES:
        issues.append("primary_mode_invalid")
    if facets.get("sceneCondition") not in SCENE_CONDITIONS:
        issues.append("scene_condition_invalid")
    if facets.get("acquisitionPattern") not in ACQUISITION_PATTERNS:
        issues.append("acquisition_pattern_invalid")
    if facets.get("subjectCondition") not in SUBJECT_CONDITIONS:
        issues.append("subject_condition_invalid")
    if facets.get("evidenceTier") not in EVIDENCE_TIERS:
        issues.append("evidence_tier_invalid")
    if not roles or any(role not in VIEW_ROLES for role in roles):
        issues.append("view_roles_invalid")
    if len(roles) != len(sources) or len(set(map(str, sources))) != len(sources):
        issues.append("source_inventory_invalid")
    if not str(session.get("opaqueSessionId", "")):
        issues.append("opaque_session_id_missing")
    if not str(session.get("identityGroupId", "")):
        issues.append("identity_group_id_missing")
    digest = session.get("sessionDigest")
    if (
        isinstance(digest, str)
        and digest
        and digest != canonical_digest(dict(session), "sessionDigest")
    ):
        issues.append("session_digest_invalid")
    return sorted(set(issues))


def _legacy_role(value: object) -> ViewRole:
    normalized = str(value).strip().lower().replace("_", "-")
    aliases: dict[str, ViewRole] = {
        "back": "rear",
        "rear": "rear",
        "front": "front",
        "left": "side",
        "right": "side",
        "left-three-quarter": "three-quarter",
        "right-three-quarter": "three-quarter",
        "three-quarter": "three-quarter",
        "detail": "detail",
    }
    if normalized not in aliases:
        raise ValueError("legacy_view_role_unsupported")
    return aliases[normalized]


def _safe_token(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, Sequence) and not isinstance(value, str | bytes) else ()
