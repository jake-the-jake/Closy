from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from closy_forge.capture import (
    RasterIngestError,
    build_synthetic_capture_record,
    delete_raster_fixture_registry,
    ingest_raster_fixture_manifest,
    score_capture_record,
)
from closy_forge.ci import export_sanitized_ci_diagnostics
from closy_forge.contracts.schema_export import checked_in_schemas_fresh, export_schemas
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.determinism import compare_package_trees
from closy_forge.pipeline.build_tshirt_demo import build_demo_tshirt_package
from closy_forge.reports.reporter import human_report, summarize_package
from closy_forge.validation.validator import validate_package
from closy_forge.visual_understanding import (
    build_default_applied_correction_record,
    build_multiview_fusion_record,
    build_tshirt_visual_observations,
)

EXIT_SUCCESS = 0
EXIT_ARGUMENT_ERROR = 2
EXIT_VALIDATION_FAILURE = 3
EXIT_BUILD_FAILURE = 4
EXIT_UNSAFE_PATH = 5


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
        if not hasattr(args, "handler"):
            parser.print_help()
            return EXIT_ARGUMENT_ERROR
        return int(args.handler(args))
    except ValueError as exc:
        print(f"closy-forge: {exc}", file=sys.stderr)
        return EXIT_UNSAFE_PATH
    except FileExistsError as exc:
        print(f"closy-forge: {exc}", file=sys.stderr)
        return EXIT_BUILD_FAILURE
    except RuntimeError as exc:
        print(f"closy-forge: {exc}", file=sys.stderr)
        return EXIT_BUILD_FAILURE


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="closy-forge",
        description="Deterministic Closy avatar-and-garment package tooling.",
    )
    subparsers = parser.add_subparsers(dest="command")

    demo = subparsers.add_parser("demo", help="Build deterministic fixture garments.")
    demo_sub = demo.add_subparsers(dest="demo_command")
    build = demo_sub.add_parser("build-tshirt", help="Build the canonical demo T-shirt package.")
    build.add_argument("--output", required=True, type=Path, help="Output .closygarment directory.")
    build.add_argument(
        "--force", action="store_true", help="Replace exactly the requested target package."
    )
    build.add_argument(
        "--seed", type=int, default=101, help="Deterministic fixture seed recorded in provenance."
    )
    build.add_argument(
        "--body-length", type=float, default=None, help="Override T-shirt body length in metres."
    )
    build.add_argument(
        "--half-chest-width",
        type=float,
        default=None,
        help="Override half chest panel width in metres.",
    )
    build.add_argument(
        "--sleeve-length", type=float, default=None, help="Override sleeve length in metres."
    )
    build.add_argument("--json", action="store_true", help="Print machine-readable result JSON.")
    build.set_defaults(handler=_build_tshirt)

    capture = subparsers.add_parser("capture", help="Build deterministic capture fixtures.")
    capture_sub = capture.add_subparsers(dest="capture_command")
    capture_demo = capture_sub.add_parser(
        "build-synthetic", help="Build a synthetic metadata-only capture record."
    )
    capture_demo.add_argument("--output", required=True, type=Path, help="Output directory.")
    capture_demo.add_argument("--force", action="store_true", help="Replace existing JSON files.")
    capture_demo.add_argument(
        "--seed", type=int, default=101, help="Deterministic fixture seed recorded in the record."
    )
    capture_demo.add_argument("--json", action="store_true", help="Print machine-readable result.")
    capture_demo.set_defaults(handler=_build_synthetic_capture)
    capture_raster = capture_sub.add_parser(
        "ingest-raster-fixture",
        help="Ingest allowlisted local synthetic PNG/JPEG fixtures into private records.",
    )
    capture_raster.add_argument("--manifest", required=True, type=Path)
    capture_raster.add_argument("--input-root", required=True, type=Path)
    capture_raster.add_argument("--private-registry", required=True, type=Path)
    capture_raster.add_argument("--portable-output", required=True, type=Path)
    capture_raster.add_argument("--force", action="store_true")
    capture_raster.add_argument(
        "--json", action="store_true", help="Print machine-readable result."
    )
    capture_raster.set_defaults(handler=_ingest_raster_fixture)
    capture_delete = capture_sub.add_parser(
        "delete-raster-fixture",
        help="Delete Forge-managed private raster fixture records and write a tombstone.",
    )
    capture_delete.add_argument("--private-registry", required=True, type=Path)
    capture_delete.add_argument("--tombstone", required=True, type=Path)
    capture_delete.add_argument("--force", action="store_true")
    capture_delete.add_argument(
        "--json", action="store_true", help="Print machine-readable result."
    )
    capture_delete.set_defaults(handler=_delete_raster_fixture)

    validate = subparsers.add_parser("validate", help="Validate a .closygarment package from disk.")
    validate.add_argument("package", type=Path)
    validate.add_argument("--json", action="store_true")
    validate.set_defaults(handler=_validate)

    report = subparsers.add_parser("report", help="Summarise a validated .closygarment package.")
    report.add_argument("package", type=Path)
    report.add_argument("--json", action="store_true")
    report.set_defaults(handler=_report)

    schemas = subparsers.add_parser("schemas", help="Export or verify checked-in JSON Schemas.")
    schema_sub = schemas.add_subparsers(dest="schema_command")
    export = schema_sub.add_parser("export", help="Export deterministic schema files.")
    export.add_argument("--output", required=True, type=Path)
    export.set_defaults(handler=_schemas_export)
    check = schema_sub.add_parser("check", help="Verify checked-in schema files are fresh.")
    check.add_argument("--schema-dir", default=Path("schemas/v1"), type=Path)
    check.add_argument("--json", action="store_true")
    check.set_defaults(handler=_schemas_check)

    packages = subparsers.add_parser("packages", help="Inspect built .closygarment packages.")
    package_sub = packages.add_subparsers(dest="package_command")
    diff = package_sub.add_parser("diff", help="Compare two package directories byte-for-byte.")
    diff.add_argument("left", type=Path)
    diff.add_argument("right", type=Path)
    diff.add_argument("--json", action="store_true")
    diff.set_defaults(handler=_packages_diff)

    ci = subparsers.add_parser("ci", help="CI-only diagnostics and guardrail helpers.")
    ci_sub = ci.add_subparsers(dest="ci_command")
    diagnostics = ci_sub.add_parser(
        "diagnostics", help="Write privacy-safe allowlisted CI diagnostics."
    )
    diagnostics.add_argument("--source-dir", required=True, type=Path)
    diagnostics.add_argument("--output", required=True, type=Path)
    diagnostics.add_argument("--label", default="forge")
    diagnostics.add_argument("--force", action="store_true")
    diagnostics.add_argument("--json", action="store_true")
    diagnostics.set_defaults(handler=_ci_diagnostics)
    return parser


def _build_tshirt(args: argparse.Namespace) -> int:
    params = _params_from_args(args)
    result = build_demo_tshirt_package(args.output, params=params, seed=args.seed, force=args.force)
    payload = {
        "status": "built",
        "package": str(result.package_dir),
        "garmentId": result.manifest["garmentId"],
        "canonicalPackageDigest": result.manifest["canonicalPackageDigest"],
        "validation": result.validation["counts"],
    }
    if args.json:
        print(canonical_dumps(payload), end="")
    else:
        print(f"Built {result.package_dir}")
        print(f"Digest: {payload['canonicalPackageDigest']}")
        print(f"Validation: {payload['validation']}")
    return EXIT_SUCCESS


def _build_synthetic_capture(args: argparse.Namespace) -> int:
    output = args.output
    record_path = output / "capture_record.json"
    quality_path = output / "capture_quality.json"
    visual_path = output / "visual_observations.json"
    correction_path = output / "correction_record.json"
    fusion_path = output / "multiview_fusion.json"
    if not args.force and any(
        path.exists()
        for path in [record_path, quality_path, visual_path, correction_path, fusion_path]
    ):
        raise FileExistsError(f"{output} already contains capture fixture files; pass --force")
    record = build_synthetic_capture_record(seed=args.seed)
    quality = score_capture_record(record)
    visual = build_tshirt_visual_observations(record)
    correction = build_default_applied_correction_record(visual)
    fusion = build_multiview_fusion_record(record, visual, correction)
    write_canonical_json(record_path, record)
    write_canonical_json(quality_path, quality)
    write_canonical_json(visual_path, visual)
    write_canonical_json(correction_path, correction)
    write_canonical_json(fusion_path, fusion)
    payload = {
        "status": "built",
        "output": str(output),
        "recordId": record["recordId"],
        "sourceRecordHash": record["immutability"]["sourceRecordHash"],
        "qualityStatus": quality["overallStatus"],
        "qualityScore": quality["overallScore"],
        "viewCount": quality["viewCount"],
        "maskCount": visual["aggregate"]["maskCount"],
        "landmarkCount": len(visual["aggregate"]["observedLandmarks"]),
        "correctionOperationCount": len(correction["operations"]),
        "fusionStatus": fusion["qualityGate"]["status"],
        "fusionCacheKey": fusion["orchestration"]["cacheKey"],
    }
    if args.json:
        print(canonical_dumps(payload), end="")
    else:
        print(f"Built synthetic capture fixture in {output}")
        print(f"Record: {payload['recordId']}")
        print(f"Quality: {payload['qualityStatus']} {payload['qualityScore']}")
    return EXIT_SUCCESS


def _ingest_raster_fixture(args: argparse.Namespace) -> int:
    try:
        payload = ingest_raster_fixture_manifest(
            manifest_path=args.manifest,
            input_root=args.input_root,
            private_registry_dir=args.private_registry,
            portable_output_dir=args.portable_output,
            force=args.force,
        )
    except RasterIngestError as exc:
        print(f"closy-forge: raster_ingest_failed:{exc.code}", file=sys.stderr)
        return EXIT_BUILD_FAILURE
    if args.json:
        print(canonical_dumps(payload), end="")
    else:
        print("Ingested synthetic raster fixtures")
        print(f"Record: {payload['recordId']}")
        print(f"Quality: {payload['qualityStatus']}")
    return EXIT_SUCCESS


def _delete_raster_fixture(args: argparse.Namespace) -> int:
    try:
        payload = delete_raster_fixture_registry(
            private_registry_dir=args.private_registry,
            tombstone_path=args.tombstone,
            force=args.force,
        )
    except RasterIngestError as exc:
        print(f"closy-forge: raster_delete_failed:{exc.code}", file=sys.stderr)
        return EXIT_BUILD_FAILURE
    if args.json:
        print(canonical_dumps(payload), end="")
    else:
        print("Deleted Forge-managed raster fixture registry records")
        print(f"Record: {payload['recordId']}")
        print(f"Status: {payload['status']}")
    return EXIT_SUCCESS


def _validate(args: argparse.Namespace) -> int:
    validation = validate_package(args.package)
    if args.json:
        print(canonical_dumps(validation), end="")
    else:
        print(json.dumps(validation, indent=2, sort_keys=True))
    return EXIT_SUCCESS if validation["status"] == "passed" else EXIT_VALIDATION_FAILURE


def _report(args: argparse.Namespace) -> int:
    if args.json:
        print(canonical_dumps(summarize_package(args.package)), end="")
    else:
        print(human_report(args.package), end="")
    return EXIT_SUCCESS


def _schemas_export(args: argparse.Namespace) -> int:
    written = export_schemas(args.output)
    print(f"Exported {len(written)} schemas to {args.output}")
    return EXIT_SUCCESS


def _schemas_check(args: argparse.Namespace) -> int:
    fresh, issues = checked_in_schemas_fresh(args.schema_dir)
    payload = {"status": "fresh" if fresh else "stale", "issues": issues}
    if args.json:
        print(canonical_dumps(payload), end="")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return EXIT_SUCCESS if fresh else EXIT_VALIDATION_FAILURE


def _packages_diff(args: argparse.Namespace) -> int:
    diff = compare_package_trees(args.left, args.right)
    if args.json:
        print(canonical_dumps(diff), end="")
    else:
        print(json.dumps(diff, indent=2, sort_keys=True))
    return EXIT_SUCCESS if diff["status"] == "identical" else EXIT_VALIDATION_FAILURE


def _ci_diagnostics(args: argparse.Namespace) -> int:
    summary = export_sanitized_ci_diagnostics(
        args.source_dir,
        args.output,
        label=args.label,
        force=args.force,
    )
    if args.json:
        print(canonical_dumps(summary), end="")
    else:
        print(f"Wrote sanitized diagnostics to {args.output}")
        print(f"Rejected inputs: {summary['rejectedInputCount']}")
    return EXIT_SUCCESS


def _params_from_args(args: argparse.Namespace) -> TShirtParameters:
    defaults = TShirtParameters()
    values = defaults.to_json()
    if args.body_length is not None:
        values["garment_body_length"] = args.body_length
    if args.half_chest_width is not None:
        values["half_chest_width"] = args.half_chest_width
    if args.sleeve_length is not None:
        values["sleeve_length"] = args.sleeve_length
    return TShirtParameters(**values)
