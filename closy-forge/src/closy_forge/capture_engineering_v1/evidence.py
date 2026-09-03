from __future__ import annotations

import copy
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.capture.source_records import build_synthetic_capture_record

from .camera_observation import fixed_avatar_body_hypothesis
from .capture_sources import (
    decode_capture_source,
    decode_video_source,
    single_image_uncertainty,
    worn_capture_qc,
)
from .common import canonical_digest, read_mapping, sha256_bytes, write_json
from .corpus import CorpusBuild, SessionSpec, mesh_for_spec, session_specs
from .corruption import run_corruption_suite
from .development_model import predict_linear_model, train_linear_model
from .fitting import BOUNDS, TARGET_FIELDS, fit_capture_to_package
from .isolation import contestant_payload, future_d0_prerequisite_report
from .ontology import migrate_legacy_mode_c, validate_session
from .protocol import load_frozen_protocol
from .quality import PixelObservation, apply_corrections, observe_pixels, view_consistency
from .uv_projection import (
    ProjectionView,
    project_views_to_panel_uv,
    projection_controls,
    render_atlas_novel_view,
)
from .video_avi import decode_uncompressed_avi

EVIDENCE_VERSION = "closy.capture_camera_material_engineering.evidence.v1"


@dataclass(frozen=True)
class DecodedSession:
    spec: SessionSpec
    observations: tuple[PixelObservation, ...]
    projection_views: tuple[ProjectionView, ...]
    source_rows: tuple[dict[str, Any], ...]
    video_report: dict[str, Any] | None
    failures: tuple[str, ...]


def build_development_evidence(
    corpus: CorpusBuild,
    *,
    corpus_root: Path,
    output_root: Path,
    package_scratch: Path,
) -> dict[str, Any]:
    protocol = load_frozen_protocol()
    specs = session_specs()
    decoded = [_decode_session(spec, corpus_root, protocol) for spec in specs]
    model = _train_model(decoded, corpus.evaluator_targets)
    write_json(output_root / "development_pixel_model.json", model)
    fitting = _evaluate_fitting(
        decoded,
        model,
        corpus.evaluator_targets,
        package_scratch=package_scratch,
    )
    uv = _evaluate_uv(decoded)
    capture = _capture_report(decoded, protocol)
    migration = _migration_report(specs)
    isolation = future_d0_prerequisite_report(
        specs,
        contestant_source_paths=[
            Path(__file__).with_name("development_model.py"),
            Path(__file__).with_name("fitting.py"),
            Path(__file__).with_name("camera_observation.py"),
            Path(__file__).with_name("quality.py"),
        ],
    )
    corruption = run_corruption_suite()
    reports = {
        "capture_decode_qc_camera.json": capture,
        "mode_c_migration.json": migration,
        "fitting_and_family_breadth.json": fitting,
        "uv_appearance.json": uv,
        "future_d0_v5_prerequisites.json": isolation,
        "corruption.json": corruption,
    }
    for name, report in reports.items():
        write_json(output_root / name, report)
    ledger = _execution_ledger(
        protocol=protocol,
        corpus=corpus.manifest,
        capture=capture,
        migration=migration,
        fitting=fitting,
        uv=uv,
        isolation=isolation,
        corruption=corruption,
    )
    write_json(output_root / "execution_ledger.json", ledger)
    summary: dict[str, Any] = {
        "schemaVersion": 1,
        "evidenceVersion": EVIDENCE_VERSION,
        "evidenceClass": "project_authored_development_only",
        "protocolDigest": protocol["protocolDigest"],
        "corpusManifestDigest": corpus.manifest["manifestDigest"],
        "reportDigests": {
            name: sha256_bytes((output_root / name).read_bytes()) for name in sorted(reports)
        },
        "ledgerDigest": ledger["ledgerDigest"],
        "literalResult": _literal_result(capture, fitting, uv, isolation, corruption),
        "promotions": {
            "d0Qualified": False,
            "researchPrototype": False,
            "alpha": False,
            "beta": False,
            "production": False,
            "realPhotoEvidence": False,
            "privateUserEvidence": False,
            "physicalAccuracy": False,
        },
        "summaryDigest": "",
    }
    summary["summaryDigest"] = canonical_digest(summary, "summaryDigest")
    write_json(output_root / "summary.json", summary)
    return summary


def _decode_session(
    spec: SessionSpec, corpus_root: Path, protocol: Mapping[str, Any]
) -> DecodedSession:
    source_root = corpus_root / "public_sources"
    capture_thresholds = _mapping(_mapping(protocol["thresholds"])["capture"])
    observations: list[PixelObservation] = []
    views: list[ProjectionView] = []
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    video_report: dict[str, Any] | None = None
    if spec.acquisition_pattern == "guided_video":
        source_id = f"source-{spec.index:03d}-video"
        data = (source_root / f"{source_id}.avi").read_bytes()
        video_report = decode_video_source(
            data,
            source_id=source_id,
            capture_thresholds=capture_thresholds,
        )
        video = decode_uncompressed_avi(data)
        for frame_index in video_report["selectedFrameIndices"]:
            frame = video.frames[int(frame_index)]
            observation = observe_pixels(frame.width, frame.height, frame.rgba)
            observations.append(observation)
            role = spec.view_roles[int(frame_index)]
            views.append(
                ProjectionView(
                    f"{source_id}#frame-{int(frame_index):02d}",
                    role,
                    frame.width,
                    frame.height,
                    frame.rgba,
                    observation,
                )
            )
        rows.append(
            {
                "sourceId": source_id,
                "mime": "video/x-msvideo",
                "decoded": True,
                "sourceFrameCount": video_report["sourceFrameCount"],
                "selectedFrameCount": len(video_report["selectedFrameIndices"]),
                "decoderVersion": video_report["decoderVersion"],
                "decoderLicense": video_report["decoderLicense"],
            }
        )
    else:
        for role_index, role in enumerate(spec.view_roles):
            source_id = f"source-{spec.index:03d}-{role_index:02d}"
            candidates = sorted(source_root.glob(f"{source_id}.*"))
            if len(candidates) != 1:
                failures.append("decode_failure")
                continue
            path = candidates[0]
            decoded = decode_capture_source(
                path,
                source_id=source_id,
                declared_mime="image/jpeg" if path.suffix == ".jpg" else "image/png",
                view_role=role,
                evidence_tier="public_project_fixture",
                known_scale_marker_meters=(0.5 if spec.primary_mode == "A" else None),
                capture_thresholds=capture_thresholds,
            )
            observations.append(decoded.observation)
            decoded_pixels = _decode_pixels_again(path)
            views.append(
                ProjectionView(
                    source_id,
                    role,
                    decoded.observation.width,
                    decoded.observation.height,
                    decoded_pixels,
                    decoded.observation,
                )
            )
            rows.append(
                {
                    **decoded.portable_record,
                    "quality": decoded.quality,
                    "camera": decoded.camera,
                }
            )
    for view in views:
        contestant_payload(
            decoded_rgba=view.rgba,
            width=view.width,
            height=view.height,
            view_role=view.role,
            metadata={
                "family": spec.family,
                "sceneCondition": spec.scene_condition,
                "acquisitionPattern": spec.acquisition_pattern,
                "subjectCondition": spec.subject_condition,
                "evidenceTier": "public_project_fixture",
            },
            allowed_metadata=protocol["allowedContestantMetadata"],
        )
    return DecodedSession(
        spec=spec,
        observations=tuple(observations),
        projection_views=tuple(views),
        source_rows=tuple(rows),
        video_report=video_report,
        failures=tuple(failures),
    )


def _decode_pixels_again(path: Path) -> bytes:
    from closy_forge.capture.raster_sources import decode_raster_fixture_pixels

    mime = "image/jpeg" if path.suffix == ".jpg" else "image/png"
    return decode_raster_fixture_pixels(path, declared_mime=mime).rgba


def _train_model(
    sessions: Sequence[DecodedSession], targets: Mapping[str, Mapping[str, float]]
) -> dict[str, Any]:
    rows = [
        (
            session.spec.family,
            session.observations[0],
            targets[session.spec.identity_group_id],
        )
        for session in sessions
        if session.spec.split == "development" and session.observations
    ]
    return train_linear_model(rows, target_fields=TARGET_FIELDS)


def _evaluate_fitting(
    sessions: Sequence[DecodedSession],
    model: Mapping[str, Any],
    targets: Mapping[str, Mapping[str, float]],
    *,
    package_scratch: Path,
) -> dict[str, Any]:
    package_scratch.mkdir(parents=True, exist_ok=True)
    validation = [session for session in sessions if session.spec.split == "validation"]
    jobs = [
        (
            session,
            dict(model),
            dict(targets[session.spec.identity_group_id]),
            str(package_scratch / f"{session.spec.opaque_session_id}.json"),
        )
        for session in validation
    ]
    with ProcessPoolExecutor(max_workers=min(8, len(jobs))) as executor:
        rows = list(executor.map(_fit_validation_job, jobs))
    route_errors: dict[str, list[float]] = {}
    for row in rows:
        for route, value in row.pop("_routeErrors", {}).items():
            route_errors.setdefault(route, []).append(float(value))
    family_rows = {
        family: [row for row in rows if row["family"] == family] for family in sorted(TARGET_FIELDS)
    }
    family_metrics = {family: _family_metrics(values) for family, values in family_rows.items()}
    route_means = {
        route: round(statistics.fmean(values), 8) if values else 1.0
        for route, values in sorted(route_errors.items())
    }
    learned = route_means.get("learned_plus_fit", 1.0)
    deterministic = route_means.get("deterministic_pixel_fit", 1.0)
    ablations = _model_ablations(sessions, model, targets)
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "fitVersion": "closy.camera_to_pattern.staged_development_fit.v1",
        "attemptedValidationIdentityCount": len(rows),
        "statusCounts": dict(sorted(Counter(str(row["status"]) for row in rows).items())),
        "failureRowsRetained": True,
        "rows": rows,
        "familyMetrics": family_metrics,
        "routeMeanNormalizedParameterError": route_means,
        "learnedPlusFitBeatsDeterministicPixelFit": learned < deterministic,
        "modelAblations": ablations,
        "groundTruthEvaluatorOnly": True,
        "fixtureIdsConsumedByPredictor": False,
        "validationRowsConsumedByTraining": False,
        "developmentCriteriaPassed": (
            len(rows) == 20
            and all(value["validPackageRate"] >= 0.75 for value in family_metrics.values())
            and learned < deterministic
        ),
        "claim": "development_only_experimental",
        "reportDigest": "",
    }
    result["reportDigest"] = canonical_digest(result, "reportDigest")
    return result


def _fit_validation_job(
    job: tuple[DecodedSession, dict[str, Any], dict[str, float], str],
) -> dict[str, Any]:
    session, model, target, package_path = job
    if not session.observations:
        return _failure_row(session.spec, "decode_failure")
    try:
        fit = fit_capture_to_package(
            family=session.spec.family,
            observations=session.observations,
            model=model,
            package_output=Path(package_path),
            seed=20_000 + session.spec.index,
        )
    except (KeyError, OSError, RuntimeError, ValueError) as error:
        return _failure_row(session.spec, f"fit_exception:{type(error).__name__}")
    alternatives: list[dict[str, Any]] = []
    route_errors: dict[str, float] = {}
    for alternative in fit["alternatives"]:
        alternative_error = _normalized_parameter_error(
            session.spec.family, alternative["parameters"], target
        )
        route = str(alternative["route"])
        route_errors[route] = alternative_error
        alternatives.append(
            {
                "route": route,
                "status": alternative["status"],
                "normalizedParameterError": alternative_error,
                "silhouetteIou": alternative["silhouetteIou"],
                "compileExecuted": alternative["compileExecuted"],
                "topologyValidatorExecuted": alternative["topologyValidatorExecuted"],
                "independentRendererExecuted": alternative["independentRendererExecuted"],
                "optimizerIterations": alternative["optimizerIterations"],
            }
        )
    selected_error = _normalized_parameter_error(
        session.spec.family, fit["selectedParameters"], target
    )
    return {
        "identityGroupId": session.spec.identity_group_id,
        "family": session.spec.family,
        "status": fit["status"],
        "selectedRoute": fit["selectedRoute"],
        "selectedNormalizedParameterError": selected_error,
        "attemptedAlternativeCount": fit["attemptedAlternativeCount"],
        "alternatives": alternatives,
        "packageValidation": fit["package"]["validationStatus"],
        "packageFailureReason": fit["package"].get("failureReason"),
        "compilerTopologySolverExecuted": bool(
            fit["package"]["compilerExecuted"]
            and fit["package"]["topologyValidatorExecuted"]
            and fit["package"]["solverExecuted"]
        ),
        "_routeErrors": route_errors,
    }


def _evaluate_uv(sessions: Sequence[DecodedSession]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for session in sessions:
        if session.spec.split != "validation" or not session.projection_views:
            continue
        _target, meshset = mesh_for_spec(session.spec)
        atlas = project_views_to_panel_uv(meshset, list(session.projection_views))
        controls = projection_controls(meshset, list(session.projection_views))
        novel = render_atlas_novel_view(meshset, atlas)
        rows.append(
            {
                "identityGroupId": session.spec.identity_group_id,
                "family": session.spec.family,
                "observedTexelFraction": round(float(atlas.lineage["observedFraction"]), 8),
                "observedTexelCount": atlas.lineage["observedTexelCount"],
                "generatedTexelCount": atlas.lineage["generatedTexelCount"],
                "controls": controls,
                "novelView": novel,
                "status": "pass"
                if controls["sourcePixelMutationChangesAtlas"]
                and controls["roleShuffleDegradesOrRejects"]
                and not controls["unavailableTargetTruthMutationChangesAtlas"]
                and controls["observedGeneratedMasksDisjoint"]
                and novel["decoded"]
                else "fail",
            }
        )
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "projection": "mesh_triangle_barycentric_source_to_surface_to_panel_uv",
        "novelViewRendererIndependent": True,
        "attemptedIdentityCount": len(rows),
        "statusCounts": dict(sorted(Counter(str(row["status"]) for row in rows).items())),
        "familyCounts": dict(sorted(Counter(str(row["family"]) for row in rows).items())),
        "rows": rows,
        "reportDigest": "",
    }
    result["reportDigest"] = canonical_digest(result, "reportDigest")
    return result


def _capture_report(
    sessions: Sequence[DecodedSession], protocol: Mapping[str, Any]
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for session in sessions:
        qualities = [
            row["quality"] for row in session.source_rows if isinstance(row.get("quality"), Mapping)
        ]
        rejected = sum(row.get("status") != "accepted" for row in qualities)
        corrected = apply_corrections(session.observations[0], []) if session.observations else None
        rows.append(
            {
                "identityGroupId": session.spec.identity_group_id,
                "mode": session.spec.primary_mode,
                "sceneCondition": session.spec.scene_condition,
                "acquisitionPattern": session.spec.acquisition_pattern,
                "decodedObservationCount": len(session.observations),
                "sourceRows": list(session.source_rows),
                "decodeFailures": list(session.failures),
                "qcRejectedSourceCount": rejected,
                "viewConsistency": round(view_consistency(session.observations), 8),
                "singleImageUncertainty": (
                    single_image_uncertainty(session.spec.view_roles[0])
                    if session.spec.acquisition_pattern == "single_image"
                    else None
                ),
                "wornCapture": (
                    worn_capture_qc(session.observations[0])
                    if session.spec.subject_condition == "fixed_synthetic_avatar"
                    and session.observations
                    else None
                ),
                "bodyHypothesis": fixed_avatar_body_hypothesis(
                    session.observations,
                    subject_condition=session.spec.subject_condition,
                ),
                "correctionReplay": corrected.portable() if corrected is not None else None,
                "video": session.video_report,
            }
        )
    actual_video = [row for row in rows if row["video"] is not None]
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "attemptedSessionCount": len(rows),
        "decodeFailureCount": sum(len(row["decodeFailures"]) for row in rows),
        "qcRejectedSourceCount": sum(int(row["qcRejectedSourceCount"]) for row in rows),
        "actualEncodedVideoClipCount": len(actual_video),
        "minimumSourceFramesPerVideo": min(
            (int(_mapping(row["video"])["sourceFrameCount"]) for row in actual_video),
            default=0,
        ),
        "decoderVersions": sorted(
            {str(_mapping(row["video"])["decoderVersion"]) for row in actual_video}
        ),
        "cameraDerivedFromAllowedObservation": True,
        "generatorCameraConsumed": False,
        "absolutePathsPersisted": False,
        "privateUserEvidence": False,
        "rows": rows,
        "thresholds": _mapping(_mapping(protocol["thresholds"])["capture"]),
        "reportDigest": "",
    }
    result["reportDigest"] = canonical_digest(result, "reportDigest")
    return result


def _migration_report(specs: Sequence[SessionSpec]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for spec in [item for item in specs if item.primary_mode == "C"]:
        legacy = copy.deepcopy(build_synthetic_capture_record())
        legacy["recordId"] = f"legacy.{spec.opaque_session_id}"
        migrated = migrate_legacy_mode_c(legacy)
        rows.append(
            {
                "identityGroupId": spec.identity_group_id,
                "status": "pass" if not validate_session(migrated) else "fail",
                "primaryMode": migrated["primaryMode"],
                "acquisitionPattern": migrated["facets"]["acquisitionPattern"],
                "duplicateFacetFieldsPersisted": migrated["legacyModeC"][
                    "duplicateFacetFieldsPersisted"
                ]
                if migrated["legacyModeC"]
                else True,
            }
        )
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "attemptedMigrationCount": len(rows),
        "rows": rows,
        "backwardReadable": all(row["status"] == "pass" for row in rows),
        "divergentDuplicateFieldsPrevented": all(
            row["duplicateFacetFieldsPersisted"] is False for row in rows
        ),
        "reportDigest": "",
    }
    result["reportDigest"] = canonical_digest(result, "reportDigest")
    return result


def _model_ablations(
    sessions: Sequence[DecodedSession],
    model: Mapping[str, Any],
    targets: Mapping[str, Mapping[str, float]],
) -> dict[str, Any]:
    validation = [
        session
        for session in sessions
        if session.spec.split == "validation" and session.observations
    ]
    normal = _prediction_mean_error(validation, model, targets)
    zero = copy.deepcopy(model)
    for family in _mapping(zero["families"]).values():
        for field in _mapping(_mapping(family)["fields"]):
            _mapping(family)["fields"][field] = [0.0] * 5
    shuffled = list(reversed([session.observations[0] for session in validation]))
    shuffled_errors = [
        _normalized_parameter_error(
            session.spec.family,
            predict_linear_model(model, session.spec.family, observation),
            targets[session.spec.identity_group_id],
        )
        for session, observation in zip(validation, shuffled, strict=True)
    ]
    zero_error = _prediction_mean_error(validation, zero, targets)
    shuffled_error = round(statistics.fmean(shuffled_errors), 8)
    occluded_error = _occluded_prediction_error(validation, model, targets)
    return {
        "normalMeanError": normal,
        "zeroWeightsMeanError": zero_error,
        "shuffledPixelsMeanError": shuffled_error,
        "occludedPixelsMeanError": occluded_error,
        "zeroWeightsDegrade": zero_error > normal,
        "shuffledPixelsDegrade": shuffled_error > normal,
        "occludedPixelsDegrade": occluded_error > normal,
    }


def _prediction_mean_error(
    sessions: Sequence[DecodedSession],
    model: Mapping[str, Any],
    targets: Mapping[str, Mapping[str, float]],
) -> float:
    values = [
        _normalized_parameter_error(
            session.spec.family,
            predict_linear_model(model, session.spec.family, session.observations[0]),
            targets[session.spec.identity_group_id],
        )
        for session in sessions
    ]
    return round(statistics.fmean(values), 8)


def _occluded_prediction_error(
    sessions: Sequence[DecodedSession],
    model: Mapping[str, Any],
    targets: Mapping[str, Mapping[str, float]],
) -> float:
    values: list[float] = []
    for session in sessions:
        view = session.projection_views[0]
        rgba = bytearray(view.rgba)
        for y in range(view.height // 3, view.height * 2 // 3):
            for x in range(view.width // 3, view.width * 2 // 3):
                offset = (y * view.width + x) * 4
                rgba[offset : offset + 4] = bytes((232, 229, 222, 255))
        try:
            observation = observe_pixels(view.width, view.height, bytes(rgba))
            prediction = predict_linear_model(model, session.spec.family, observation)
            error = _normalized_parameter_error(
                session.spec.family, prediction, targets[session.spec.identity_group_id]
            )
        except ValueError:
            error = 1.0
        values.append(error)
    return round(statistics.fmean(values), 8)


def _normalized_parameter_error(
    family: str, predicted: Mapping[str, Any], target: Mapping[str, Any]
) -> float:
    errors = []
    for field in TARGET_FIELDS[family]:
        minimum, maximum = BOUNDS[family][field]
        errors.append(abs(float(predicted[field]) - float(target[field])) / (maximum - minimum))
    return round(statistics.fmean(errors), 8)


def _family_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    valid = [row for row in rows if row["status"] == "valid"]
    errors = [float(row["selectedNormalizedParameterError"]) for row in valid]
    return {
        "attemptedIdentityCount": len(rows),
        "validPackageCount": len(valid),
        "validPackageRate": round(len(valid) / max(1, len(rows)), 8),
        "meanNormalizedParameterError": round(statistics.fmean(errors), 8) if errors else 1.0,
    }


def _failure_row(spec: SessionSpec, status: str) -> dict[str, Any]:
    return {
        "identityGroupId": spec.identity_group_id,
        "family": spec.family,
        "status": status,
        "selectedNormalizedParameterError": 1.0,
        "attemptedAlternativeCount": 0,
        "alternatives": [],
        "packageValidation": "not_run",
        "packageFailureReason": status,
        "compilerTopologySolverExecuted": False,
    }


def _execution_ledger(**facts: Mapping[str, Any]) -> dict[str, Any]:
    capture = facts["capture"]
    fitting = facts["fitting"]
    uv = facts["uv"]
    isolation = facts["isolation"]
    corruption = facts["corruption"]
    rows = [
        _ledger_row("BP-CAPTURE-ONTOLOGY", "complete", "shared_composable_session_model"),
        _ledger_row(
            "BP-CAPTURE-DECODE",
            "complete" if capture["decodeFailureCount"] == 0 else "partial",
            f"{capture['attemptedSessionCount']}_sessions_{capture['actualEncodedVideoClipCount']}_videos",
        ),
        _ledger_row("BP-CAMERA-OBSERVATION", "complete", "pixel_mask_landmark_derived"),
        _ledger_row(
            "BP-CAMERA-PATTERN-FIT",
            "partial",
            str(fitting["statusCounts"]),
            limitation="development_only_no_real_or_hidden_evidence",
        ),
        _ledger_row(
            "BP-SOURCE-PANEL-UV",
            "complete" if uv["statusCounts"].get("fail", 0) == 0 else "partial",
            str(uv["statusCounts"]),
        ),
        _ledger_row(
            "BP-D0-V5-PREREQUISITES",
            "partial" if isolation["status"] == "pass" else "failed",
            "qualification_not_run",
            limitation="two_in_repository_renderers_are_not_hidden_scientific_sources",
        ),
        _ledger_row(
            "BP-CAPTURE-CORRUPTION",
            "complete" if corruption["allExpectedOutcomesObserved"] else "failed",
            f"{corruption['passCount']}_of_{corruption['attemptCount']}",
        ),
    ]
    ledger: dict[str, Any] = {
        "schemaVersion": 1,
        "ledgerVersion": "closy.capture_camera_material_engineering.execution_ledger.v1",
        "rows": rows,
        "historicalOutcomesAppendOnly": True,
        "qualificationRun": False,
        "ledgerDigest": "",
    }
    ledger["ledgerDigest"] = canonical_digest(ledger, "ledgerDigest")
    return ledger


def _ledger_row(
    requirement_id: str,
    status: str,
    literal_result: str,
    *,
    limitation: str = "project_authored_development_only",
) -> dict[str, Any]:
    return {
        "requirementId": requirement_id,
        "scope": "PR_C_capture_camera_fitting_uv",
        "exactSource": "capture_engineering_v1",
        "exactExecutable": "scripts/build_capture_engineering_v1.py",
        "executionKind": "deterministic_project_authored_fixture_execution",
        "platformToolchain": "host_cpu_python_3_11_or_3_12",
        "dataProvenance": "project_authored_synthetic_public_fixture",
        "avatarProfile": "fixed_synthetic_alpha_beta",
        "garmentFamily": "tshirt_sleeveless_top_simple_skirt",
        "evidenceTier": "public_project_fixture_development_only",
        "denominators": "frozen_protocol_manifest",
        "status": status,
        "literalResult": literal_result,
        "limitations": [limitation],
        "unsupportedTiers": ["future_licensed_public", "future_private_authorized"],
        "firstUnmetPredicate": None if status == "complete" else limitation,
        "nextDependency": "external_hidden_sources_or_real_authorized_data",
        "sourceLockResultPublicationRunIdentities": "protocol_corpus_reports_exact_head_ci",
    }


def _literal_result(
    capture: Mapping[str, Any],
    fitting: Mapping[str, Any],
    uv: Mapping[str, Any],
    isolation: Mapping[str, Any],
    corruption: Mapping[str, Any],
) -> str:
    passed = (
        capture["decodeFailureCount"] == 0
        and fitting["attemptedValidationIdentityCount"] == 20
        and fitting["developmentCriteriaPassed"] is True
        and uv["attemptedIdentityCount"] == 20
        and uv["statusCounts"].get("fail", 0) == 0
        and isolation["status"] == "pass"
        and corruption["allExpectedOutcomesObserved"] is True
    )
    return "development_acceptance_pass" if passed else "development_acceptance_partial"


def verify_generated_evidence(output_root: Path) -> list[str]:
    issues: list[str] = []
    summary = read_mapping(output_root / "summary.json")
    if summary.get("evidenceVersion") != EVIDENCE_VERSION:
        issues.append("summary_version_invalid")
    if summary.get("summaryDigest") != canonical_digest(summary, "summaryDigest"):
        issues.append("summary_digest_invalid")
    ledger = read_mapping(output_root / "execution_ledger.json")
    if ledger.get("ledgerDigest") != canonical_digest(ledger, "ledgerDigest"):
        issues.append("ledger_digest_invalid")
    return issues


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
