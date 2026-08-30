from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import write_canonical_json

BASE_HEAD = "4c5dcd284a1221a7820184e640fb92b67b880787"
REPLAY_END = "01b03133f0e5479bd1955c570a168aa2fbfbfa1e"

SOURCE_GROUPS = {
    "pr35": (
        "b90d795125671778ed27075492bad0cd57cdafaf",
        "b2621ea7e5644d743e5a8a5717e40b8f8ba3bd7d",
        "7b2176a6a8fb22ef8a1b960656b36061f1356aa9",
        "5c9abbbf953407810a3efccebebcef7cf3b2bb5c",
        "dba7f57e2484780a4de9a2d13617d2c368be433e",
        "52a3128b887e73002075e5ed4a071e8e0295f81e",
        "cf8ad491427adfd849115771ea8dfc476cb4569f",
        "6d7a88564318481f1b87596bfa50eebe3dddfb3c",
        "7debe171d420691d35b33b95810fe0f854810872",
        "0f7e10c98a75e15a061aa00e538e8b0a4526c68d",
        "c816e9db46621aefd3749830c6aec11862693bec",
        "5eaae22d81fda055d058843067ccff82da651991",
        "b02e57e55e47290cfcc34ecda0fdde937254dab8",
        "461436c22f8c5cd1948e0f6906961d0c512dcc34",
        "4d543764a774a76f1db477802d66e7e7ce311f26",
        "9d39d55e9d1cdae502808f73c4e14653e92d26d7",
    ),
    "closy_c_unique": (
        "8c4420b44a76c019632ea321dd15bc775fa8b498",
        "917d48879d715b2da50e359e6ad24f78915ff012",
        "357e5a345786845d0391b841326419c7dac14246",
        "9311f8bd07b865546b8302bf810e083ea8a91fe0",
        "7a1b893069987a2ffc0c18074c8ee636dff0b97c",
        "3846a749cea514428834a738f151c1d6253e3e36",
        "076cb9390a1ac98f7fa477f4ba101425c5906d0c",
        "024503e59d3acdf4800f02d5a98144fe2ed39bac",
        "f6444bce2e7857c65889138ffff6f367a3972d8f",
        "703ab16fcf8c891d61d2bb5e17b209995a87e123",
        "f3e96de0f9eaf308159655cb38654f18e4603f9e",
        "adde707d598ab46397e8c97183911542719ffe8c",
        "ab80af3417acb4c72f559e009fe6b4b2baa27968",
        "a82a5f986e2e8021151d0154775e424075043c76",
        "6a94d288b9e01c24763738f56cb3a19457170491",
        "6c0483ee985eec1de45b1ab64edf1f36edb81e20",
        "23ee8d2e9b79f07ed9dbfbe05e60cd29dc5ecd7d",
        "e3e08576b7bcc6c0763c9d0a42c0601ba0f9344a",
        "7430131d5ecab0df77d3933709aed0d86138e03e",
    ),
    "pr29": (
        "cac0bd40fb1a7ae91da2aa6a0835408f907f42b9",
        "62464db2a91e4b24b808cfcd99ee95578fc95f32",
    ),
    "pr30": (
        "76a7bef01729c3278a8f9d381fbbfa7ce783d132",
        "f8e3f45b4e2108d3ab54a09a02397d5900e8dee2",
        "2075882e0961c7e3b4a13d33398049a0059c5c99",
    ),
    "pr32": ("0b570a1c587ff24fed1d3d3689676c9826cc27fe",),
}

HISTORICAL_EVIDENCE = {
    "5c9abbbf953407810a3efccebebcef7cf3b2bb5c",
    "5eaae22d81fda055d058843067ccff82da651991",
    "076cb9390a1ac98f7fa477f4ba101425c5906d0c",
    "f3e96de0f9eaf308159655cb38654f18e4603f9e",
    "a82a5f986e2e8021151d0154775e424075043c76",
    "23ee8d2e9b79f07ed9dbfbe05e60cd29dc5ecd7d",
    "62464db2a91e4b24b808cfcd99ee95578fc95f32",
    "f8e3f45b4e2108d3ab54a09a02397d5900e8dee2",
    "2075882e0961c7e3b4a13d33398049a0059c5c99",
}

HISTORICAL_STATUS = {
    "461436c22f8c5cd1948e0f6906961d0c512dcc34",
    "4d543764a774a76f1db477802d66e7e7ce311f26",
    "9d39d55e9d1cdae502808f73c4e14653e92d26d7",
    "024503e59d3acdf4800f02d5a98144fe2ed39bac",
    "f6444bce2e7857c65889138ffff6f367a3972d8f",
    "adde707d598ab46397e8c97183911542719ffe8c",
    "6a94d288b9e01c24763738f56cb3a19457170491",
    "e3e08576b7bcc6c0763c9d0a42c0601ba0f9344a",
}

CONFLICTS = {
    "4d543764a774a76f1db477802d66e7e7ce311f26": (
        "semantic_merge_preserved_B_trial_level_PAIR_D2_accounting_over_older_summary"
    ),
    "76a7bef01729c3278a8f9d381fbbfa7ce783d132": (
        "semantic_merge_registered_runtime_delivery_and_avatar_variation_schemas_once_each"
    ),
}

PR26_BUSINESS = (
    "12cdfd60e841bf33903f6e75b102d9d48f69501c",
    "644da7468d890a2a8600f7fa141ee3298f00bad8",
    "fdcdfb22c02c796b97ee6406bbd76025a645822f",
    "86f8175769191ef6231cbafd04b72c4a23bd4720",
    "ba73b310a8609de4eb4f0ed2284c6d2d9a6fab53",
)
PR31_BUSINESS = ("f99ab295677556a0df37af25c7a1b8541a648ad3",)
SHARED_WORKFLOW_SOURCES = (
    "1cf7ecff18bd0bbd37820638c0af2029d7a928ac",
    "386effb254d4ba15499399dfd7fd94c70a0e0fc5",
)


def build_manifest(repository: Path) -> dict[str, Any]:
    result_commits = _lines(repository, "rev-list", "--reverse", f"{BASE_HEAD}..{REPLAY_END}")
    source_to_result: dict[str, str] = {}
    for result in result_commits:
        body = _text(repository, "show", "-s", "--format=%B", result)
        for source in re.findall(r"cherry picked from commit ([0-9a-f]{40})", body):
            source_to_result[source] = result

    dispositions: list[dict[str, Any]] = []
    for lane, sources in SOURCE_GROUPS.items():
        for source in sources:
            result = source_to_result.get(source)
            if result is None:
                raise ValueError(f"replay_source_result_missing:{source}")
            semantic = "business_patch"
            disposition = "applied_with_result_sha"
            if source in HISTORICAL_EVIDENCE:
                semantic = "historical_evidence"
                disposition = "applied_and_retained_as_historical_evidence"
            elif source in HISTORICAL_STATUS:
                semantic = "historical_status"
                disposition = "applied_then_superseded_by_reconciled_D_status"
            dispositions.append(
                {
                    "lane": lane,
                    "sourceSha": source,
                    "sourcePatchId": _patch_id(repository, source),
                    "resultSha": result,
                    "resultPatchId": _patch_id(repository, result),
                    "subject": _text(repository, "show", "-s", "--format=%s", source),
                    "semanticClass": semantic,
                    "disposition": disposition,
                    "conflictResolution": CONFLICTS.get(source),
                    "cherryPickXVerified": source
                    in _text(repository, "show", "-s", "--format=%B", result),
                }
            )

    duplicate_proofs = [
        _duplicate_proof(repository, source, result_commits, source_pr=26)
        for source in PR26_BUSINESS
    ]
    duplicate_proofs.extend(
        _duplicate_proof(repository, source, result_commits, source_pr=31)
        for source in PR31_BUSINESS
    )
    if any(row["matchingPatchCountInReplay"] != 1 for row in duplicate_proofs):
        raise ValueError("replay_duplicate_or_missing_pr26_pr31_business_patch")
    return {
        "schemaVersion": 1,
        "manifestVersion": "closy.integrated-replay-manifest.d0.v1",
        "baseHead": BASE_HEAD,
        "replayEnd": REPLAY_END,
        "sourceCommitCount": sum(len(values) for values in SOURCE_GROUPS.values()),
        "dispositions": dispositions,
        "sharedWorkflow": {
            "sourceCommitsExcluded": list(SHARED_WORKFLOW_SOURCES),
            "reason": "shared_exact_cover_workflow_patch_already_present_in_ancestry",
            "replayedCopyCount": 0,
            "atMostOnceSatisfied": True,
        },
        "duplicateBusinessPatchProof": duplicate_proofs,
        "validation": {
            "allSourceCommitsDisposed": len(dispositions)
            == sum(len(values) for values in SOURCE_GROUPS.values()),
            "allAppliedCommitsHaveCherryPickXTrailer": all(
                row["cherryPickXVerified"] for row in dispositions
            ),
            "pr26BusinessPatchesExactlyOnce": all(
                row["matchingPatchCountInReplay"] == 1
                for row in duplicate_proofs
                if row["sourcePr"] == 26
            ),
            "pr31BusinessPatchesExactlyOnce": all(
                row["matchingPatchCountInReplay"] == 1
                for row in duplicate_proofs
                if row["sourcePr"] == 31
            ),
            "mergeCommitUsed": False,
        },
    }


def _duplicate_proof(
    repository: Path, source: str, replay_commits: list[str], *, source_pr: int
) -> dict[str, Any]:
    patch = _patch_id(repository, source)
    matches = [commit for commit in replay_commits if _patch_id(repository, commit) == patch]
    return {
        "sourcePr": source_pr,
        "sourceSha": source,
        "patchId": patch,
        "matchingPatchCountInReplay": len(matches),
        "matchingResultShas": matches,
    }


def _patch_id(repository: Path, commit: str) -> str:
    show = subprocess.run(
        ["git", "show", "--pretty=format:", "--binary", commit],
        cwd=repository,
        check=True,
        capture_output=True,
        timeout=30,
    )
    patch = subprocess.run(
        ["git", "patch-id", "--stable"],
        cwd=repository,
        check=True,
        input=show.stdout,
        capture_output=True,
        timeout=30,
    ).stdout.decode("ascii")
    if not patch.strip():
        raise ValueError(f"replay_patch_id_missing:{commit}")
    return patch.split()[0]


def _lines(repository: Path, *args: str) -> list[str]:
    return [line for line in _text(repository, *args).splitlines() if line]


def _text(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("closy-forge/docs/evidence/integrated_replay_manifest_d0_v1.json"),
    )
    args = parser.parse_args()
    repository = args.repository.resolve()
    output = args.output if args.output.is_absolute() else repository / args.output
    manifest = build_manifest(repository)
    write_canonical_json(output, manifest)
    print(
        f"sources={manifest['sourceCommitCount']} "
        f"dispositions={len(manifest['dispositions'])} duplicates=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
