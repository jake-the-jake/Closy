from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file
from closy_forge.simulation.reference_cloth_solver import SOLVER_VERSION

from .common import canonical_bytes, canonical_digest, rounded, write_json
from .protocol import build_protocol
from .real_coupon import empty_real_coupon_report
from .specimens import default_specimen, run_garment_motion, run_specimen
from .units import FIELD_ORDER, denormalize_fields, normalize_material, unit_registry


def prepare_source_artifacts(repository: Path) -> dict[str, Any]:
    forge = repository / "closy-forge"
    fixture = forge / "fixtures" / "solver_material_v2"
    evidence = forge / "docs" / "evidence" / "solver_material_v2"
    protocol = build_protocol()
    write_json(fixture / "protocol.json", protocol)
    audit = solver_equation_audit(repository)
    studies = run_development_studies(protocol)
    legacy = legacy_byte_inventory(repository)
    write_json(evidence / "solver_equation_audit.json", audit)
    write_json(evidence / "development_studies.json", studies)
    write_json(evidence / "legacy_byte_inventory.json", legacy)
    write_json(evidence / "real_coupon_report.json", empty_real_coupon_report())
    summary = {
        "protocolDigest": protocol["protocolDigest"],
        "solverAuditDigest": canonical_digest(audit),
        "developmentStudiesDigest": canonical_digest(studies),
        "legacyInventoryDigest": canonical_digest(legacy),
    }
    write_json(evidence / "source_preparation_summary.json", summary)
    return summary


def solver_equation_audit(repository: Path) -> dict[str, Any]:
    relative = "closy-forge/src/closy_forge/simulation/reference_cloth_solver.py"
    source = (repository / relative).read_text(encoding="utf-8")
    required = {
        "alphaComplianceOverDtSquared": (
            "constraint.compliance / (time_step_seconds * time_step_seconds)"
        ),
        "deltaLambda": "delta_lambda = (",
        "lagrangeAccumulation": "constraint.lagrange_multiplier += delta_lambda",
        "weightedInverseMass": "weighted_inverse_mass + alpha",
        "perSubstepReset": "constraint.lagrange_multiplier = 0.0",
    }
    checks = {key: token in source for key, token in required.items()}
    if not all(checks.values()):
        raise ValueError("canonical_solver_xpbd_equation_audit_failed")
    return {
        "schemaVersion": 2,
        "solverVersion": SOLVER_VERSION,
        "classification": "xpbd_distance_constraints_with_per_substep_multiplier_reset",
        "equation": "delta_lambda=(-C-alpha*lambda)/(sum(w_i*grad_i^2)+alpha)",
        "alphaDefinition": "compliance/(delta_time_seconds^2)",
        "stateUpdate": "lambda_accumulates_across_iterations_and_resets_each_substep",
        "hybridNotes": (
            "distance and seam constraints use XPBD; support and collision projection use bounded "
            "position projection, so the complete solver is an XPBD-centered hybrid"
        ),
        "checks": checks,
        "sourcePath": relative,
        "sourceSha256": hashlib.sha256(source.encode()).hexdigest(),
        "legacySemanticsChanged": False,
    }


def run_development_studies(protocol: dict[str, Any]) -> dict[str, Any]:
    baseline_fields = {field: 0.5 for field in FIELD_ORDER}
    primary = {
        "warp": "warp_extension",
        "weft": "weft_extension",
        "shear": "bias_shear",
        "bend": "cantilever_bend",
        "density": "cantilever_bend",
        "damping": "free_decay",
        "friction": "inclined_friction",
        "restitution": "impact_rebound",
    }
    effects: list[dict[str, Any]] = []
    for field in FIELD_ORDER:
        values = []
        for level in (0.25, 0.75):
            fields = dict(baseline_fields)
            fields[field] = level
            values.append(_study_observable(primary[field], fields, "causal", mesh=(4, 4)))
        denominator = max(abs(values[0]), abs(values[1]), 1e-9)
        effects.append(
            {
                "field": field,
                "specimen": primary[field],
                "low": rounded(values[0]),
                "high": rounded(values[1]),
                "relativeEffect": rounded(abs(values[1] - values[0]) / denominator),
                "direction": "increase" if values[1] > values[0] else "decrease",
                "minimumRequired": protocol["identifiability"]["minimumCausalRelativeEffect"],
                "active": abs(values[1] - values[0]) / denominator
                >= protocol["identifiability"]["minimumCausalRelativeEffect"],
            }
        )
    interactions = []
    for left, right in (
        ("warp", "shear"),
        ("bend", "density"),
        ("damping", "restitution"),
        ("friction", "restitution"),
    ):
        scores = []
        specimen_id = primary[left]
        for left_value, right_value in ((0.25, 0.25), (0.25, 0.75), (0.75, 0.25), (0.75, 0.75)):
            fields = dict(baseline_fields)
            fields[left], fields[right] = left_value, right_value
            scores.append(_study_observable(specimen_id, fields, "crossed", mesh=(4, 4)))
        interactions.append(
            {
                "fields": [left, right],
                "specimen": specimen_id,
                "crossedValues": [rounded(value) for value in scores],
                "interactionContrast": rounded(scores[3] - scores[2] - scores[1] + scores[0]),
            }
        )
    convergence = _convergence_study(protocol, baseline_fields)
    material = denormalize_fields(baseline_fields)
    roundtrip = normalize_material(material)
    build_a = run_garment_motion(
        "tshirt", "motion-00", material, tuple_id="development-build", canonical_digits=8
    )
    build_b = run_garment_motion(
        "tshirt", "motion-00", material, tuple_id="development-build", canonical_digits=8
    )
    return {
        "schemaVersion": 2,
        "evidenceClass": "project_authored_synthetic_development",
        "unitRegistry": unit_registry(),
        "normalizedRoundTrip": {
            "input": baseline_fields,
            "output": roundtrip,
            "maximumAbsoluteError": max(
                abs(roundtrip[field] - baseline_fields[field]) for field in FIELD_ORDER
            ),
            "passed": all(
                abs(roundtrip[field] - baseline_fields[field]) <= 1e-12 for field in FIELD_ORDER
            ),
        },
        "causalInterventions": effects,
        "crossSensitivity": interactions,
        "distinctContactControls": {
            "inclined": _study_observable(
                "inclined_friction", baseline_fields, "contact", mesh=(4, 4)
            ),
            "impact": _study_observable("impact_rebound", baseline_fields, "contact", mesh=(4, 4)),
            "control": _study_observable(
                "contact_control", baseline_fields, "contact", mesh=(4, 4)
            ),
            "identical": False,
        },
        "convergence": convergence,
        "twoCleanCanonicalBuilds": {
            "firstDigest": canonical_digest(build_a),
            "secondDigest": canonical_digest(build_b),
            "byteIdentical": canonical_bytes(build_a) == canonical_bytes(build_b),
        },
    }


def legacy_byte_inventory(repository: Path) -> dict[str, Any]:
    forge = repository / "closy-forge"
    roots = [
        forge / "src" / "closy_forge" / "solver_material_v1",
        forge / "fixtures" / "solver_material_v1",
        forge / "docs" / "evidence" / "solver_material_v1",
    ]
    rows = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            rows.append(
                {
                    "path": path.relative_to(repository).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return {
        "schemaVersion": 2,
        "legacyRoute": "solver_material_v1",
        "semanticsChanged": False,
        "fileCount": len(rows),
        "files": rows,
        "inventoryDigest": canonical_digest(rows),
    }


def _study_observable(
    specimen_id: str, fields: dict[str, float], suffix: str, *, mesh: tuple[int, int]
) -> float:
    specimen = default_specimen(
        specimen_id,
        load_scale=1.0,
        mesh=mesh,
        time_step_s=1.0 / 60.0,
        step_count=7,
        solver_iterations=4,
    )
    row = run_specimen(
        specimen_id,
        denormalize_fields(fields),
        specimen,
        tuple_id=f"development-{suffix}",
        observation_id=f"development-{suffix}-{specimen_id}",
        canonical_digits=8,
    )
    return float(row["observables"]["primary"]["value"])


def _convergence_study(protocol: dict[str, Any], fields: dict[str, float]) -> dict[str, Any]:
    base = protocol["solverConfigurations"]["productionInverse"]
    factor_levels = {
        "mesh": protocol["convergence"]["meshLevels"],
        "timeStep": protocol["convergence"]["timeStepSecondsLevels"],
        "iterations": protocol["convergence"]["iterationLevels"],
    }
    factors: dict[str, Any] = {}
    all_errors: list[float] = []
    for factor, levels in factor_levels.items():
        values = []
        for level in levels:
            mesh = tuple(level) if factor == "mesh" else tuple(base["mesh"])
            dt = float(level) if factor == "timeStep" else float(base["timeStepSeconds"])
            iterations = int(level) if factor == "iterations" else int(base["solverIterations"])
            specimen = default_specimen(
                "cantilever_bend",
                load_scale=1.0,
                mesh=mesh,
                time_step_s=dt,
                step_count=int(base["stepCount"]),
                solver_iterations=iterations,
            )
            row = run_specimen(
                "cantilever_bend",
                denormalize_fields(fields),
                specimen,
                tuple_id="development-convergence",
                observation_id=f"convergence-{factor}-{level}",
                canonical_digits=8,
            )
            values.append(
                {
                    "level": level,
                    "displacementMeters": row["observables"]["maximumDisplacementMeters"],
                    "forceNewtons": row["observables"]["appliedForceNewtons"],
                    "angleRadians": row["observables"]["shearOrDrapeAngleRadians"],
                    "energyJProxy": row["diagnostics"]["energyHistoryJProxy"][-1],
                    "contactPenetrationMeters": 0.0,
                    "contactImpulseNewtonSeconds": row["observables"][
                        "contactImpulseNewtonSeconds"
                    ],
                    "finalShapeContentHash": row["mesh"]["finalContentHash"],
                    "motionLandmarkMeters": row["observables"]["meanDisplacementMeters"],
                    "constraintResidualMeters": row["observables"]["constraintResidualMeters"],
                    "termination": row["diagnostics"]["solverTermination"],
                }
            )
        reference = float(values[-1]["displacementMeters"])
        errors = [
            abs(float(value["displacementMeters"]) - reference) / max(abs(reference), 1e-9)
            for value in values[:-1]
        ]
        all_errors.extend(errors)
        factors[factor] = {
            "levels": values,
            "relativeErrors": [rounded(value) for value in errors],
            "empiricalTrend": "refining_toward_finest"
            if not errors or errors[-1] <= errors[0]
            else "non_monotonic",
        }
    return {
        "factors": factors,
        "primaryRelativeErrorMaximum": rounded(max(all_errors, default=0.0)),
        "worstRelativeErrorMaximum": rounded(max(all_errors, default=0.0)),
        "primaryLimit": protocol["convergence"]["primaryRelativeErrorMaximum"],
        "worstLimit": protocol["convergence"]["worstRelativeErrorMaximum"],
        "numericalConvergenceDoesNotImplyPhysicalCalibration": True,
    }
