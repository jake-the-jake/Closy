from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes

GRAMMAR_VERSION = "closy.structured_pattern_grammar.d0.v1"
DATASET_VERSION = "closy.synthetic_pattern_dataset.d0.v1"
BENCHMARK_VERSION = "closy.template_retrieval_benchmark.d0.v1"

TEMPLATES: tuple[dict[str, Any], ...] = (
    {"id": "template.sleeveless_top", "category": "top", "panelCount": 2, "openings": 4},
    {"id": "template.long_sleeved_top", "category": "top", "panelCount": 4, "openings": 4},
    {"id": "template.simple_skirt", "category": "bottom", "panelCount": 2, "openings": 2},
    {"id": "template.simple_trousers", "category": "bottom", "panelCount": 4, "openings": 3},
    {"id": "template.simple_dress", "category": "one_piece", "panelCount": 4, "openings": 4},
    {"id": "template.button_shirt", "category": "top", "panelCount": 5, "openings": 5},
    {"id": "template.jacket_outerwear", "category": "outerwear", "panelCount": 7, "openings": 5},
    {
        "id": "template.layered_asymmetric",
        "category": "layered_unusual",
        "panelCount": 4,
        "openings": 8,
    },
)


def build_pattern_inference_foundation(*, seed: int = 101) -> dict[str, Any]:
    grammar = _grammar()
    dataset = _dataset(seed)
    split = _split(dataset)
    benchmark = _benchmark(dataset, split)
    correction = _correction(dataset["samples"][0])
    bundle: dict[str, Any] = {
        "schemaVersion": 1,
        "foundationVersion": "closy.pattern_inference_foundation.d0.v1",
        "grammar": grammar,
        "dataset": dataset,
        "split": split,
        "correction": correction,
        "benchmark": benchmark,
        "evidenceTier": {
            "deterministicTemplateBaselineExecuted": True,
            "syntheticPublicFixtureOnly": True,
            "trainedModelRun": False,
            "learnedAccuracyClaimed": False,
            "privateDatasetUsed": False,
        },
        "integrity": {"bundleHash": ""},
    }
    bundle["integrity"]["bundleHash"] = _hash(bundle, "bundleHash")
    issues = validate_pattern_inference_foundation(bundle)
    if issues:
        raise ValueError(";".join(issues))
    return bundle


def write_pattern_inference_foundation(output: Path, *, seed: int = 101) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    bundle = build_pattern_inference_foundation(seed=seed)
    files = {
        "grammar.json": bundle["grammar"],
        "synthetic_dataset.json": bundle["dataset"],
        "split.json": bundle["split"],
        "correction_record.json": bundle["correction"],
        "benchmark.json": bundle["benchmark"],
        "foundation.json": bundle,
    }
    for name, payload in files.items():
        write_canonical_json(output / name, payload)
    return bundle


def rank_templates(observation: dict[str, Any]) -> list[dict[str, Any]]:
    category = str(observation.get("category", "unknown"))
    panel_count = int(observation.get("panelCount", 0))
    openings = int(observation.get("openings", 0))
    ranked = []
    for template in TEMPLATES:
        losses = {
            "categoryMismatch": 0 if category == template["category"] else 1,
            "panelCountDistance": abs(panel_count - int(template["panelCount"])),
            "openingCountDistance": abs(openings - int(template["openings"])),
        }
        score = (
            losses["categoryMismatch"] * 100
            + losses["panelCountDistance"] * 10
            + losses["openingCountDistance"]
        )
        ranked.append({"templateId": template["id"], "score": score, "losses": losses})
    return sorted(ranked, key=lambda item: (item["score"], item["templateId"]))


def validate_pattern_inference_foundation(bundle: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    grammar = bundle.get("grammar", {})
    dataset = bundle.get("dataset", {})
    split = bundle.get("split", {})
    benchmark = bundle.get("benchmark", {})
    correction = bundle.get("correction", {})
    if grammar.get("grammarVersion") != GRAMMAR_VERSION:
        issues.append("pattern_grammar_version_invalid")
    productions = grammar.get("productions", [])
    template_ids = {item["id"] for item in TEMPLATES}
    if {item.get("templateId") for item in productions} != template_ids:
        issues.append("pattern_grammar_template_set_invalid")
    samples = dataset.get("samples", [])
    sample_ids = [str(item.get("sampleId")) for item in samples]
    if len(samples) != 24 or len(set(sample_ids)) != len(sample_ids):
        issues.append("synthetic_pattern_dataset_invalid")
    if len({int(item.get("features", {}).get("panelCount", 0)) for item in samples}) < 4:
        issues.append("variable_panel_count_evidence_missing")
    split_ids = {key: set(map(str, split.get(key, []))) for key in ("train", "validation", "test")}
    samples_by_id = {str(item.get("sampleId")): item for item in samples}
    split_templates = {
        name: {
            str(samples_by_id[sample_id].get("targetTemplateId"))
            for sample_id in ids
            if sample_id in samples_by_id
        }
        for name, ids in split_ids.items()
    }
    identity_leakage = any(
        split_templates[left] & split_templates[right]
        for left, right in (
            ("train", "validation"),
            ("train", "test"),
            ("validation", "test"),
        )
    )
    if (
        any(not ids for ids in split_ids.values())
        or any(
            split_ids[a] & split_ids[b]
            for a, b in (("train", "validation"), ("train", "test"), ("validation", "test"))
        )
        or set().union(*split_ids.values()) != set(sample_ids)
    ):
        issues.append("pattern_dataset_split_invalid")
    if split.get("identityLeakage") is not identity_leakage:
        issues.append("pattern_dataset_identity_leakage_claim_invalid")
    if benchmark.get("actualBaselineRun") is not True or benchmark.get("sampleCount") != 24:
        issues.append("template_retrieval_benchmark_invalid")
    expected_correct = sum(
        rank_templates(item["features"])[0]["templateId"] == item["targetTemplateId"]
        for item in samples
    )
    if benchmark.get("top1Correct") != expected_correct:
        issues.append("template_retrieval_benchmark_recompute_mismatch")
    if (
        correction.get("humanCorrectionRecord") is not False
        or correction.get("simulatedCorrectionFixture") is not True
        or correction.get("humanReviewStatus") != "not_run"
        or correction.get("sourceKind") != "project_authored_synthetic_fixture"
    ):
        issues.append("pattern_correction_record_invalid")
    tier = bundle.get("evidenceTier", {})
    if (
        tier.get("trainedModelRun") is not False
        or tier.get("learnedAccuracyClaimed") is not False
        or tier.get("privateDatasetUsed") is not False
    ):
        issues.append("pattern_inference_evidence_tier_overclaim")
    if bundle.get("integrity", {}).get("bundleHash") != _hash(bundle, "bundleHash"):
        issues.append("pattern_inference_bundle_hash_mismatch")
    return issues


def _grammar() -> dict[str, Any]:
    productions = [
        {
            "templateId": template["id"],
            "category": template["category"],
            "panelCount": {"minimum": template["panelCount"], "maximum": template["panelCount"]},
            "openingCount": template["openings"],
            "geometryRules": [
                "panel_boundaries_are_simple",
                "seam_spans_reference_existing_edges",
                "openings_are_not_sewn_closed",
            ],
        }
        for template in TEMPLATES
    ]
    return {
        "schemaVersion": 1,
        "grammarVersion": GRAMMAR_VERSION,
        "domain": "human_avatar_garments_only",
        "productions": productions,
        "supportsVariablePanelCount": True,
    }


def _dataset(seed: int) -> dict[str, Any]:
    samples = []
    for template in TEMPLATES:
        for variant in range(3):
            sample_id = f"sample.{str(template['id']).split('.')[-1]}.{variant:02d}"
            samples.append(
                {
                    "sampleId": sample_id,
                    "seed": seed + variant,
                    "source": "project_authored_synthetic_fixture",
                    "features": {
                        "category": template["category"],
                        "panelCount": template["panelCount"],
                        "openings": template["openings"],
                        "easeVariant": variant - 1,
                    },
                    "targetTemplateId": template["id"],
                    "containsPrivateData": False,
                }
            )
    return {
        "schemaVersion": 1,
        "datasetVersion": DATASET_VERSION,
        "seed": seed,
        "samples": samples,
        "generatedByLearnedModel": False,
    }


def _split(dataset: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, list[str]] = {"train": [], "validation": [], "test": []}
    for sample in dataset["samples"]:
        variant = int(str(sample["sampleId"]).rsplit(".", 1)[1])
        groups[("train", "validation", "test")[variant]].append(sample["sampleId"])
    return {
        "schemaVersion": 1,
        "splitVersion": "closy.pattern_dataset_split.d0.v1",
        **groups,
        "identityLeakage": True,
        "identityLeakageStatus": "known_baseline_defect_template_identity_crosses_all_splits",
        "splitPolicy": "variant_zero_train_one_validation_two_test",
    }


def _benchmark(dataset: dict[str, Any], split: dict[str, Any]) -> dict[str, Any]:
    records = []
    for sample in dataset["samples"]:
        ranking = rank_templates(sample["features"])
        records.append(
            {
                "sampleId": sample["sampleId"],
                "expectedTemplateId": sample["targetTemplateId"],
                "selectedTemplateId": ranking[0]["templateId"],
                "selectedScore": ranking[0]["score"],
                "split": next(
                    key
                    for key in ("train", "validation", "test")
                    if sample["sampleId"] in split[key]
                ),
            }
        )
    correct = sum(item["expectedTemplateId"] == item["selectedTemplateId"] for item in records)
    return {
        "schemaVersion": 1,
        "benchmarkVersion": BENCHMARK_VERSION,
        "baseline": "deterministic_template_retrieval_not_learned",
        "actualBaselineRun": True,
        "sampleCount": len(records),
        "top1Correct": correct,
        "top1Accuracy": round(correct / len(records), 9),
        "records": records,
        "trainedModelCompared": False,
        "generalisationClaimed": False,
    }


def _correction(sample: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "correctionVersion": "closy.pattern_correction_record.d0.v1",
        "recordId": "correction.synthetic_pattern_reference_v1",
        "sampleId": sample["sampleId"],
        "beforeTemplateId": "template.long_sleeved_top",
        "afterTemplateId": sample["targetTemplateId"],
        "changedFields": ["templateId"],
        "reasonCode": "project_authored_wrong_template_fixture",
        "humanCorrectionRecord": False,
        "simulatedCorrectionFixture": True,
        "humanReviewStatus": "not_run",
        "sourceKind": "project_authored_synthetic_fixture",
        "containsPrivateData": False,
    }


def _hash(document: dict[str, Any], field: str) -> str:
    payload = deepcopy(document)
    payload["integrity"][field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
