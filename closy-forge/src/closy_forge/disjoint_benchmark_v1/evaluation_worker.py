from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes

from .compiler import compile_structural_candidate, reference_mesh_metrics
from .metrics import appearance_predicates, compare_rasters, observable_parameter_errors
from .renderers import render_evaluator_target


def evaluate_routes(
    predictions: Mapping[str, Any],
    targets: Mapping[str, Any],
    *,
    route_ids: list[str],
    appearance_ordinals: set[int],
) -> dict[str, Any]:
    target_by_id = {str(item["opaqueId"]): item for item in targets["identities"]}
    records: list[dict[str, Any]] = []
    compile_count = 0
    appearance_count = 0
    for prediction in predictions["predictions"]:
        if prediction["routeId"] not in route_ids:
            continue
        target = target_by_id[str(prediction["opaqueId"])]
        try:
            candidate_compile = compile_structural_candidate(prediction["parameters"])
            target_compile = compile_structural_candidate(target["parameters"])
            compile_count += 1
            candidate_render = render_evaluator_target(
                prediction["parameters"],
                prediction["appearance"],
                target["capture"]["evaluatorThreeQuarter"],
            )
            target_render = render_evaluator_target(
                target["parameters"],
                target["appearance"],
                target["capture"]["evaluatorThreeQuarter"],
            )
            raster = compare_rasters(candidate_render, target_render)
            parameter = observable_parameter_errors(prediction["parameters"], target["parameters"])
            reference = reference_mesh_metrics(
                candidate_compile.rest_mesh, target_compile.rest_mesh
            )
            applicable_appearance = int(target["ordinal"]) in appearance_ordinals
            appearance = None
            if applicable_appearance:
                appearance = appearance_predicates(
                    candidate_render, target_render, target["appearance"]
                )
                appearance_count += 1
            compile_report = candidate_compile.report
            required_openings = {
                "opening.neck",
                "opening.hem",
                "opening.cuff.left",
                "opening.cuff.right",
            }
            structural_pass = (
                compile_report["finite"]
                and compile_report["bindingStatus"] == "pass"
                and compile_report["seamStatus"] == "pass"
                and set(compile_report["openingIds"]) == required_openings
                and not compile_report["solverExecuted"]
            )
            records.append(
                {
                    "opaqueId": prediction["opaqueId"],
                    "ordinal": target["ordinal"],
                    "stratum": target["stratum"],
                    "routeId": prediction["routeId"],
                    "status": "pass" if structural_pass else "fail",
                    "predictionHash": prediction["predictionHash"],
                    "parameterMetrics": parameter,
                    "rasterMetrics": raster,
                    "reference3dMetrics": reference,
                    "compile": compile_report,
                    "appearance": appearance,
                    "failureClassification": None
                    if structural_pass
                    else "canonical_structural_compile_failed",
                }
            )
        except (ValueError, KeyError, TypeError) as error:
            records.append(
                {
                    "opaqueId": prediction.get("opaqueId"),
                    "ordinal": target.get("ordinal"),
                    "stratum": target.get("stratum"),
                    "routeId": prediction.get("routeId"),
                    "status": "fail",
                    "predictionHash": prediction.get("predictionHash"),
                    "parameterMetrics": {"macroNormalizedError": 1.0, "worstNormalizedError": 1.0},
                    "rasterMetrics": {"silhouetteIoU": 0.0},
                    "reference3dMetrics": {"rmsVertexErrorMeters": 1.0},
                    "compile": None,
                    "appearance": None,
                    "failureClassification": f"exception:{type(error).__name__}:{error}",
                }
            )
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "workerVersion": "closy.d0_disjoint.evaluation_worker.v1",
        "routeIds": route_ids,
        "identityCount": len(target_by_id),
        "compileCount": compile_count,
        "appearanceEvaluationCount": appearance_count,
        "solverExecuted": False,
        "records": records,
        "workerHash": "",
    }
    report["workerHash"] = _hash({**report, "workerHash": ""})
    return report


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--targets", required=True)
    parser.add_argument("--routes", required=True)
    parser.add_argument("--appearance-ordinals", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    predictions = json.loads(Path(args.predictions).read_text(encoding="utf-8"))
    targets = json.loads(Path(args.targets).read_text(encoding="utf-8"))
    report = evaluate_routes(
        predictions,
        targets,
        route_ids=args.routes.split(","),
        appearance_ordinals={int(value) for value in args.appearance_ordinals.split(",") if value},
    )
    write_canonical_json(Path(args.output), report)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
