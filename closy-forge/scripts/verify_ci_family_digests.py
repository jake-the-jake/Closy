from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

EXPECTED_FAMILIES = {
    "tshirt",
    "sleeveless",
    "long-sleeved",
    "simple-skirt",
    "simple-trousers",
    "simple-dress",
    "button-shirt",
    "jacket-outerwear",
    "layered-asymmetric",
}
EXPECTED_ENVIRONMENT_COUNT = 3


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify family digests across CI environments.")
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--family-index-output", type=Path)
    args = parser.parse_args()

    observations: dict[str, list[dict[str, object]]] = defaultdict(list)
    reports = sorted(args.input_root.rglob("family-shard-*.json"))
    if len(reports) != 9:
        raise SystemExit(f"expected 9 family shard reports, found {len(reports)}")
    for report_path in reports:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for item in report.get("families", []):
            observations[str(item["family"])].append(item)

    if set(observations) != EXPECTED_FAMILIES:
        raise SystemExit("family digest matrix is incomplete")
    family_records = []
    for family, items in sorted(observations.items()):
        digests = [str(item["canonicalDigest"]) for item in items]
        if len(items) != EXPECTED_ENVIRONMENT_COUNT:
            raise SystemExit(f"{family}: expected 3 environment results, found {len(items)}")
        if len(set(digests)) != 1:
            raise SystemExit(f"{family}: cross-platform or cross-minor byte drift: {digests}")
        validation_passed = all(item.get("validationStatus") == "passed" for item in items)
        physical_accepted = all(item.get("physicalQualityAccepted") is True for item in items)
        inter_layer_values = {item.get("interLayerCollisionEnabled") for item in items}
        if len(inter_layer_values) != 1:
            raise SystemExit(f"{family}: inter-layer evidence drift: {sorted(inter_layer_values)}")
        inter_layer_collision = next(iter(inter_layer_values))
        family_records.append(
            {
                "canonicalDigest": digests[0],
                "family": family,
                "interLayerCollisionEnabled": inter_layer_collision,
                "physicalQualityAccepted": physical_accepted,
                "validationPassed": validation_passed,
            }
        )
        print(f"{family}: {digests[0]}")
    phase8_complete = (
        all(
            record["validationPassed"] is True and record["physicalQualityAccepted"] is True
            for record in family_records
        )
        and next(
            record["interLayerCollisionEnabled"]
            for record in family_records
            if record["family"] == "layered-asymmetric"
        )
        is True
    )
    index = {
        "families": family_records,
        "phase8FamilyLadderComplete": phase8_complete,
        "reason": (
            "all_validated_physical_and_layer_contact_evidence_passed"
            if phase8_complete
            else "one_or_more_physical_or_layer_contact_gates_partial"
        ),
        "schemaVersion": 1,
        "source": "validated_cross_environment_family_artifacts",
    }
    if args.family_index_output is not None:
        args.family_index_output.parent.mkdir(parents=True, exist_ok=True)
        args.family_index_output.write_text(
            json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
