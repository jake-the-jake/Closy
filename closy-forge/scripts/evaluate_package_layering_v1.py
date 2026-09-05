from __future__ import annotations

import argparse
import copy
import ctypes
import importlib
import os
import platform
import shutil
import subprocess
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import read_glb_meshset, write_indexed_glb
from closy_forge.geometry.mesh_model import add, scale
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.package_layering_v1.contacts import contacts
from closy_forge.package_layering_v1.contracts import LayerSpec, load_layers
from closy_forge.package_layering_v1.matrix import STATES, cases
from closy_forge.package_layering_v1.solver import SETTINGS, solve, validate_output
from closy_forge.simulation.reference_cloth_solver import flatten_mesh
from closy_forge.simulation.self_collision import build_triangle_refs


def peak_memory() -> int | None:
    if os.name != "nt":
        resource = importlib.import_module("resource")
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024

    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t)
            for name in (
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
            )
        ]

    counter = Counters()
    counter.cb = ctypes.sizeof(counter)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(Counters),
        ctypes.c_ulong,
    )
    ctypes.windll.psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    process = ctypes.windll.kernel32.GetCurrentProcess()
    if not ctypes.windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(counter), counter.cb):
        return None
    return int(counter.PeakWorkingSetSize)


def refresh_family(root: Path) -> None:
    doc = read_json(root / "manifest.json")
    for row in doc["inventory"]:
        p = root / row["path"]
        row["sha256"], row["byteSize"] = sha256_file(p), p.stat().st_size
    doc.pop("packageIdentity")
    doc["packageIdentity"] = sha256_bytes(canonical_dumps(doc).encode())
    write_canonical_json(root / "manifest.json", doc)


def negatives(source: Path, root: Path, outfit: Path | None) -> list[dict[str, Any]]:
    source_top, source_bottom = source / "tshirt/nominal", source / "simple_trousers/nominal"
    base = [LayerSpec("a", source_top), LayerSpec("b", source_bottom)]
    order = [("a", "b", 0.0, 2.0, True)]
    rows = []
    declarations = (
        "cycle",
        "missing",
        "duplicate",
        "units",
        "avatar",
        "stale_binding",
        "impossible_clearance",
        "geometry",
        "nonfinite_geometry",
        "nonfinite_material",
        "opening_policy",
        "tampered_report",
        "forged_empty_witnesses",
    )
    for kind in declarations:
        test = list(base)
        orders = list(order)
        try:
            if kind == "cycle":
                orders.append(("b", "a", 0, 2, True))
            elif kind == "missing":
                orders = [("a", "missing", 0, 2, True)]
            elif kind == "duplicate":
                test[1] = replace(test[1], layer_id="a")
            elif kind == "impossible_clearance":
                test[0] = replace(test[0], body_clearance_m=1)
            elif kind == "nonfinite_material":
                test[0] = replace(test[0], density_kg_m2=float("nan"))
            elif kind == "opening_policy":
                test[0] = replace(test[0], opening_policy="seal_all")
            elif kind in {"tampered_report", "forged_empty_witnesses"}:
                if outfit is None:
                    rows.append(
                        {
                            "case": kind,
                            "terminal": "not_run",
                            "reason": "no_executed_contact_output",
                        }
                    )
                    continue
                copied = root / kind
                shutil.copytree(outfit, copied)
                report = read_json(copied / "report.json")
                if kind == "tampered_report":
                    report["after"]["maximumThicknessDeficitM"] = -1
                else:
                    report["beforeWitnesses"] = []
                    report["before"]["contactCount"] = 0
                    report["executed"] = True
                write_canonical_json(copied / "report.json", report)
                # Re-sign local fixture so the independent measurement check, not just SHA,
                # must catch dishonest aggregates. Trust remains external in normal loading.
                manifest = read_json(copied / "manifest.json")
                for row in manifest["inventory"]:
                    row["sha256"] = sha256_file(copied / row["path"])
                    row["byteSize"] = (copied / row["path"]).stat().st_size
                manifest.pop("identity")
                manifest["identity"] = sha256_bytes(canonical_dumps(manifest).encode())
                write_canonical_json(copied / "manifest.json", manifest)
                validate_output(copied, trusted_manifest_hash=sha256_file(copied / "manifest.json"))
                raise RuntimeError("negative_not_rejected")
            else:
                copied = root / kind
                shutil.copytree(source_top, copied)
                test[0] = replace(test[0], package=copied)
                if kind in {"units", "avatar"}:
                    doc = read_json(copied / "manifest.json")
                    doc["units" if kind == "units" else "avatarId"] = "wrong"
                    write_canonical_json(copied / "manifest.json", doc)
                elif kind == "stale_binding":
                    path = copied / "binding/sim_to_render.bin"
                    data = bytearray(path.read_bytes())
                    data[32] ^= 1
                    path.write_bytes(data)
                else:
                    path = copied / "simulation/simulation_mesh.glb"
                    mesh = read_glb_meshset(path)
                    first = mesh.meshes[0]
                    if kind == "geometry":
                        a, b, _ = first.triangles[0]
                        first.vertices[b] = first.vertices[a]
                    else:
                        first.vertices[0] = (float("nan"), 0, 0)
                    write_indexed_glb(path, mesh, "invalid", (1, 0, 0, 1))
                refresh_family(copied)
            load_layers(test, orders)
        except (ValueError, KeyError, IndexError) as error:
            rows.append({"case": kind, "terminal": "passed_rejection", "reason": str(error)})
        except Exception as error:
            rows.append({"case": kind, "terminal": "failed", "reason": str(error)})
        else:
            rows.append({"case": kind, "terminal": "failed", "reason": "negative_not_rejected"})
    return rows


def run(source: Path, root: Path) -> dict[str, Any]:
    if root.exists():
        raise ValueError("matrix_output_must_be_fresh")
    root.mkdir(parents=True)
    declared = cases(source)

    def layer_json(spec: LayerSpec) -> dict[str, Any]:
        data = asdict(spec)
        data["package"] = str(spec.package)
        return data

    protocol: dict[str, Any] = {
        "version": "package_layering_matrix_v1",
        "classification": "exposed_host_cpu_development",
        "positiveCases": [
            {
                "caseId": c.case_id,
                "intent": c.intent,
                "layers": [layer_json(s) for s in c.layers],
                "order": c.order,
            }
            for c in declared
        ],
        "poseStates": [asdict(s) for s in STATES],
        "stateDenominator": 40,
        "adjacentSampleDenominator": 30,
        "adjacentFractions": [0.5],
        "adjacentScope": "interpolated_corrected_cage_contacts_only_not_CCD",
        "thresholds": asdict(SETTINGS),
        "negativeDenominator": 13,
        "rationale": (
            "8mm_existing_seam_budget_0.16mm_reference_contact_residual_"
            "45mm_bounded_development_projection"
        ),
        "physicalFabric": False,
        "mobilePerformance": "not_run",
    }
    write_canonical_json(root / "protocol.json", protocol)
    forge = Path(__file__).resolve().parents[1]
    sources = {
        p.relative_to(forge).as_posix(): sha256_file(p)
        for p in [
            *sorted((forge / "src").rglob("*.py")),
            Path(__file__).resolve(),
            forge / "tests/unit/test_package_layering_v1.py",
            forge / "tests/unit/test_package_layering_security_v1.py",
        ]
    }
    write_canonical_json(
        root / "source_inventory.json",
        {
            "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "files": sources,
        },
    )
    rows, adjacent = [], []
    contact_output = None
    start = time.perf_counter()
    for case in declared:
        for state in STATES:
            output = root / case.case_id / state.state_id
            try:
                layers = load_layers(list(case.layers), list(case.order))
                report = solve(layers, list(case.order), state, output)
                after = copy.deepcopy(report["after"])
                after.pop("witnesses")
                row = {
                    "caseId": case.case_id,
                    "pose": state.state_id,
                    "terminal": "passed" if report["ready"] else "quality_failed",
                    "geometryValid": True,
                    "before": report["before"],
                    "after": after,
                    "manifestHash": sha256_file(output / "manifest.json"),
                    "wallSeconds": report["wallSeconds"],
                    "cpuSeconds": report["cpuSeconds"],
                    "peakProcessMemoryBytes": peak_memory(),
                }
                if report["before"]["contactCount"]:
                    contact_output = output
            except Exception as error:
                row = {
                    "caseId": case.case_id,
                    "pose": state.state_id,
                    "terminal": "failed",
                    "reason": f"{type(error).__name__}:{error}",
                }
            rows.append(row)
            write_canonical_json(root / "checkpoint.json", {"rows": rows, "next": len(rows) + 1})
            print(f"{len(rows)}/40 {case.case_id}/{state.state_id} {row['terminal']}", flush=True)
        for left, right in zip(STATES, STATES[1:], strict=False):
            try:
                first_root, second_root = (
                    root / case.case_id / left.state_id,
                    root / case.case_id / right.state_id,
                )
                a, b = (
                    read_glb_meshset(first_root / "simulation.glb"),
                    read_glb_meshset(second_root / "simulation.glb"),
                )
                points = [
                    scale(add(x, y), 0.5)
                    for x, y in zip(
                        flatten_mesh(a).positions, flatten_mesh(b).positions, strict=True
                    )
                ]
                refs, _ = build_triangle_refs(a)
                context = read_json(first_root / "context.json")
                _, observed = contacts(
                    points, refs, context["triangleLayers"], context["materials"], context["order"]
                )
                adjacent.append(
                    {
                        "caseId": case.case_id,
                        "from": left.state_id,
                        "to": right.state_id,
                        "fraction": 0.5,
                        "terminal": "executed",
                        **observed,
                    }
                )
            except Exception as error:
                adjacent.append(
                    {
                        "caseId": case.case_id,
                        "from": left.state_id,
                        "to": right.state_id,
                        "terminal": "failed",
                        "reason": str(error),
                    }
                )
    controls = negatives(source, root / "negatives", contact_output)
    result = {
        "version": "package_layering_result_v1",
        "protocolHash": sha256_file(root / "protocol.json"),
        "host": platform.platform(),
        "rows": rows,
        "denominator": 40,
        "qualityPassed": sum(r["terminal"] == "passed" for r in rows),
        "validGeometry": sum(r.get("geometryValid", False) for r in rows),
        "failed": sum(r["terminal"] == "failed" for r in rows),
        "adjacentSamples": adjacent,
        "negatives": controls,
        "wallSeconds": time.perf_counter() - start,
        "physicalQualification": False,
        "dynamicZ2": False,
        "sourcesUnchanged": all(sha256_file(forge / p) == value for p, value in sources.items()),
    }
    write_canonical_json(root / "result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--families", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run(args.families.resolve(), args.output.resolve())
    return int(
        result["failed"] > 0
        or not result["sourcesUnchanged"]
        or any(r["terminal"] != "passed_rejection" for r in result["negatives"])
    )


if __name__ == "__main__":
    raise SystemExit(main())
