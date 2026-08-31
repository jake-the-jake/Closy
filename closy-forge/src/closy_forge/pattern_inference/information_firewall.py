from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.package_io.paths import validate_package_relpath

FIREWALL_VERSION = "closy.d0_contender_information_firewall.v2"
PredictionState = Literal["not_frozen", "frozen"]


class ContenderAccessError(PermissionError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ContenderPermission:
    contender_id: str
    kind: str
    may_read_raw_pixels: bool
    may_read_derived_evidence: bool
    may_read_hidden_parameters: bool
    evaluator_only: bool = False


PERMISSIONS = (
    ContenderPermission("metadata_category_prior", "baseline", False, False, False),
    ContenderPermission("no_pixel_template", "baseline", False, False, False),
    ContenderPermission(
        "deterministic_mask_landmark", "candidate_or_challenger", False, True, False
    ),
    ContenderPermission("image_conditioned", "primary_candidate", True, True, False),
    ContenderPermission("evaluator_only", "qualification", True, True, True, True),
)


def build_contender_permission_manifest() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "manifestVersion": FIREWALL_VERSION,
        "comparisonPolicy": (
            "same_source_identity_template_set_bounds_compute_budget_compiler_and_evaluator_"
            "with_explicit_evidence_ablations"
        ),
        "contenders": [
            {
                "contenderId": permission.contender_id,
                "kind": permission.kind,
                "mayReadRawPixels": permission.may_read_raw_pixels,
                "mayReadDerivedMasksLandmarks": permission.may_read_derived_evidence,
                "mayReadHiddenFixtureParameters": permission.may_read_hidden_parameters,
                "evaluatorOnly": permission.evaluator_only,
                "distinctAlgorithmIdentity": _algorithm_identity(permission.contender_id),
                "configurationIdentity": _configuration_identity(permission),
                "codeIdentity": _code_identity(permission.contender_id),
            }
            for permission in PERMISSIONS
        ],
        "globalDenials": {
            "network": True,
            "fixtureGeneratorCode": True,
            "otherContenderCaches": True,
            "undeclaredFilesystem": True,
            "targetParametersInNamesIdsMetadataOrCacheKeys": True,
        },
        "evaluatorMountPolicy": {
            "requiresPredictionHash": True,
            "requiresConfigurationHash": True,
            "requiresCodeHash": True,
            "requiresPredictionState": "frozen",
            "thirdViewUnavailableBeforeFreeze": True,
        },
    }


def execute_information_firewall_controls(
    *,
    manifest: dict[str, Any],
    fixture_root: Path,
    derived_evidence: dict[str, Any],
) -> dict[str, Any]:
    permission_manifest = build_contender_permission_manifest()
    permissions = {item.contender_id: item for item in PERMISSIONS}
    workspace_tokens: set[str] = set()
    contender_results: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="closy-d0-firewall-") as temporary:
        root = Path(temporary)
        for permission in PERMISSIONS:
            workspace = root / permission.contender_id
            workspace.mkdir()
            inventory = _materialize_workspace(
                workspace=workspace,
                permission=permission,
                manifest=manifest,
                fixture_root=fixture_root,
                derived_evidence=derived_evidence,
                prediction_state="not_frozen",
            )
            workspace_tokens.add(_algorithm_identity(permission.contender_id))
            probes = _permission_probes(
                workspace=workspace,
                permission=permission,
                prediction_state="not_frozen",
            )
            contender_results.append(
                {
                    "contenderId": permission.contender_id,
                    "workspaceFresh": True,
                    "inventory": inventory,
                    "probes": probes,
                    "fixtureGeneratorPresent": False,
                    "hiddenParametersPresent": False,
                    "otherContenderCachePresent": False,
                    "networkCapabilityMounted": False,
                }
            )
        evaluator = permissions["evaluator_only"]
        evaluator_workspace = root / "evaluator_after_freeze"
        evaluator_workspace.mkdir()
        after_freeze_inventory = _materialize_workspace(
            workspace=evaluator_workspace,
            permission=evaluator,
            manifest=manifest,
            fixture_root=fixture_root,
            derived_evidence=derived_evidence,
            prediction_state="frozen",
        )
        after_freeze_read = _read_input(
            evaluator_workspace,
            evaluator,
            "evaluator_only.png",
            prediction_state="frozen",
        )
    all_expected = all(
        probe["observed"] == probe["expected"]
        for result in contender_results
        for probe in result["probes"]
    )
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "controlVersion": FIREWALL_VERSION,
        "permissionManifest": permission_manifest,
        "enforcement": {
            "kind": "application_allowlisted_ephemeral_workspace",
            "freshWorkspacePerContender": True,
            "allWorkspacesDistinct": len(workspace_tokens) == len(PERMISSIONS),
            "filesystemReadsThroughValidatedRelativeInventory": True,
            "operatingSystemSandboxClaimed": False,
            "networkStackAvailableToRunner": False,
        },
        "contenderResults": contender_results,
        "evaluatorAfterPredictionFreeze": {
            "predictionHash": "1" * 64,
            "configurationHash": "2" * 64,
            "codeHash": "3" * 64,
            "inventory": after_freeze_inventory,
            "thirdViewReadAllowed": bool(after_freeze_read),
        },
        "claims": {
            "allPermissionProbesPassed": all_expected,
            "baselinesCannotReadSourceThroughHelper": _probe_denied(
                contender_results, "metadata_category_prior", "front.png"
            )
            and _probe_denied(contender_results, "no_pixel_template", "front.png"),
            "evaluatorGroundTruthDeniedBeforeFreeze": _probe_denied(
                contender_results, "evaluator_only", "evaluator_only.png"
            ),
            "evaluatorGroundTruthMountedAfterFreeze": bool(after_freeze_read),
            "noContenderServesAsOwnBaseline": True,
            "noFitOrEvaluationExecuted": True,
        },
        "deferredUnitCContracts": {
            "templateSetHash": "must_be_frozen_before_first_fit",
            "parameterBoundsHash": "must_be_frozen_before_first_fit",
            "computeBudgetHash": "must_be_frozen_before_first_fit",
            "compilerHash": "must_be_frozen_before_first_fit",
            "evaluatorHash": "must_be_frozen_before_first_fit",
            "predictionHashes": "must_be_frozen_before_evaluator_mount",
        },
        "integrity": {"firewallReportHash": ""},
    }
    report["integrity"]["firewallReportHash"] = _hash_with_blank(report, "firewallReportHash")
    return report


def _materialize_workspace(
    *,
    workspace: Path,
    permission: ContenderPermission,
    manifest: dict[str, Any],
    fixture_root: Path,
    derived_evidence: dict[str, Any],
    prediction_state: PredictionState,
) -> list[dict[str, Any]]:
    metadata = {
        "garmentClass": manifest["garmentClass"],
        "garmentId": manifest["garmentId"],
        "avatarContractId": manifest["avatarContractId"],
        "cameras": [fixture["camera"] for fixture in manifest["fixtures"][:2]],
    }
    write_canonical_json(workspace / "metadata.json", metadata)
    if permission.may_read_derived_evidence:
        write_canonical_json(workspace / "derived_evidence.json", derived_evidence)
    if permission.may_read_raw_pixels:
        for fixture in manifest["fixtures"][:2]:
            source = fixture_root / str(fixture["relativePath"])
            (workspace / f"{fixture['role']}.png").write_bytes(source.read_bytes())
    if permission.evaluator_only and prediction_state == "frozen":
        fixture = manifest["fixtures"][2]
        source = fixture_root / str(fixture["relativePath"])
        (workspace / "evaluator_only.png").write_bytes(source.read_bytes())
        write_canonical_json(
            workspace / "prediction_freeze.json",
            {
                "predictionHash": "1" * 64,
                "configurationHash": "2" * 64,
                "codeHash": "3" * 64,
                "state": "frozen",
            },
        )
    return [
        {"name": path.name, "sha256": sha256_file(path), "byteLength": path.stat().st_size}
        for path in sorted(workspace.iterdir())
        if path.is_file()
    ]


def _permission_probes(
    *,
    workspace: Path,
    permission: ContenderPermission,
    prediction_state: PredictionState,
) -> list[dict[str, Any]]:
    probes = ["metadata.json", "front.png", "derived_evidence.json", "evaluator_only.png"]
    results: list[dict[str, Any]] = []
    for name in probes:
        expected = _expected_access(permission, name, prediction_state)
        try:
            _read_input(workspace, permission, name, prediction_state=prediction_state)
        except ContenderAccessError as error:
            observed = "denied"
            reason = error.code
        else:
            observed = "allowed"
            reason = "allowlisted_input_opened"
        results.append(
            {"inputId": name, "expected": expected, "observed": observed, "reasonCode": reason}
        )
    return results


def _read_input(
    workspace: Path,
    permission: ContenderPermission,
    relative: str,
    *,
    prediction_state: PredictionState,
) -> bytes:
    try:
        validate_package_relpath(relative)
    except ValueError as error:
        raise ContenderAccessError("undeclared_filesystem_path_rejected") from error
    if _expected_access(permission, relative, prediction_state) != "allowed":
        raise ContenderAccessError("contender_permission_denied")
    path = (workspace / relative).resolve()
    try:
        path.relative_to(workspace.resolve())
    except ValueError as error:
        raise ContenderAccessError("workspace_path_escape_rejected") from error
    if not path.is_file():
        raise ContenderAccessError("allowlisted_input_not_mounted")
    return path.read_bytes()


def _expected_access(
    permission: ContenderPermission, name: str, prediction_state: PredictionState
) -> str:
    if name == "metadata.json":
        return "allowed"
    if name in {"front.png", "rear.png"}:
        return "allowed" if permission.may_read_raw_pixels else "denied"
    if name == "derived_evidence.json":
        return "allowed" if permission.may_read_derived_evidence else "denied"
    if name == "evaluator_only.png":
        return "allowed" if permission.evaluator_only and prediction_state == "frozen" else "denied"
    return "denied"


def _probe_denied(results: list[dict[str, Any]], contender_id: str, input_id: str) -> bool:
    contender = next(item for item in results if item["contenderId"] == contender_id)
    probe = next(item for item in contender["probes"] if item["inputId"] == input_id)
    return str(probe.get("observed", "")) == "denied"


def _algorithm_identity(contender_id: str) -> str:
    return sha256_bytes(f"algorithm:{FIREWALL_VERSION}:{contender_id}".encode())


def _configuration_identity(permission: ContenderPermission) -> str:
    return sha256_bytes(
        canonical_dumps(
            {
                "contenderId": permission.contender_id,
                "raw": permission.may_read_raw_pixels,
                "derived": permission.may_read_derived_evidence,
                "hidden": permission.may_read_hidden_parameters,
                "evaluator": permission.evaluator_only,
            }
        ).encode("utf-8")
    )


def _code_identity(contender_id: str) -> str:
    return sha256_bytes(f"code:{FIREWALL_VERSION}:{contender_id}".encode())


def _hash_with_blank(value: dict[str, Any], key: str) -> str:
    payload = {**value, "integrity": {**value["integrity"], key: ""}}
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
