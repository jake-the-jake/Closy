from __future__ import annotations

import io
import re
import secrets
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

from .common import canonical_bytes, canonical_digest, sha256_bytes, write_json
from .producer_cross import render_cross_generator
from .producer_in_model import render_in_model
from .protocol import validate_protocol
from .render_types import RenderedObservation, mask_runs
from .safe_private_io import SafePrivateRoot
from .video_mjpeg import decode_mjpeg_avi, encode_mjpeg_avi

HEX256 = re.compile(r"^[0-9a-f]{64}$")
PUBLIC_SESSION_FIELDS = frozenset(
    {
        "sessionId",
        "partition",
        "mode",
        "family",
        "declaredCalibrationTargetType",
        "expectedSourceCount",
        "expectedVideoFrames",
        "sources",
        "allowedFieldsOnly",
        "truthWithheld",
        "truthCommitment",
    }
)
PUBLIC_SOURCE_FIELDS = frozenset(
    {
        "sourceId",
        "kind",
        "contentAddressedName",
        "sourceSha256",
        "container",
        "codec",
        "width",
        "height",
        "decodedFrameCount",
        "framesPerSecond",
        "coarseCaptureRole",
        "weakView",
    }
)


def generate_corpus(
    protocol: dict[str, Any],
    *,
    partition: str,
    public_root: Path,
    evaluator_root: Path,
    frozen_source_commit: str,
    frozen_source_tree: str,
    seed_authority: dict[str, str],
) -> dict[str, Any]:
    failures = validate_protocol(protocol)
    if failures:
        raise ValueError(";".join(failures))
    if partition not in {"development", "locked"}:
        raise ValueError("capture_partition_invalid")
    sessions = [row for row in protocol["sessionPlan"] if row["partition"] == partition]
    expected_ids = {str(row["sessionId"]) for row in sessions}
    if set(seed_authority) != expected_ids:
        raise ValueError("capture_seed_authority_denominator_invalid")
    if len(set(seed_authority.values())) != len(seed_authority):
        raise ValueError("capture_seed_authority_overlap")
    if any(
        len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
        for value in seed_authority.values()
    ):
        raise ValueError("capture_seed_authority_format_invalid")
    source_count = sum(int(row["expectedSourceCount"]) for row in sessions)
    budget = protocol["artifactBudget"]
    planned_maximum = source_count * int(budget["maximumSourceFileBytes"])
    if planned_maximum > int(budget["maximumOwnLayerBytes"]):
        raise ValueError("capture_planned_corpus_budget_exceeded")
    public_root.mkdir(parents=True, exist_ok=True)
    evaluator_root.mkdir(parents=True, exist_ok=True)
    public_rows: list[dict[str, Any]] = []
    commitment_rows: list[dict[str, Any]] = []
    source_bytes_by_digest: dict[str, bytes] = {}
    actual_total = 0
    with SafePrivateRoot(evaluator_root) as private:
        for session in sessions:
            session_id = str(session["sessionId"])
            hidden_seed = seed_authority[session_id]
            public_row, truth_row, sources = _generate_session(
                session,
                protocol,
                frozen_source_commit=frozen_source_commit,
                hidden_seed=hidden_seed,
            )
            truth_payload = canonical_bytes(truth_row)
            truth_digest = sha256_bytes(truth_payload)
            private.write_atomic(f"{session_id}.truth.json", truth_payload)
            public_row["truthCommitment"] = truth_digest
            public_rows.append(public_row)
            commitment_rows.append(
                {
                    "sessionId": session_id,
                    "truthCommitment": truth_digest,
                    "seedCommitment": sha256_bytes(bytes.fromhex(hidden_seed)),
                    "observableManifestDigest": canonical_digest(public_row),
                }
            )
            for suffix, payload in sources:
                if len(payload) > int(budget["maximumSourceFileBytes"]):
                    raise ValueError("capture_source_file_budget_exceeded")
                digest = sha256_bytes(payload)
                source_bytes_by_digest.setdefault(f"{digest}.{suffix}", payload)
                actual_total += len(payload)
    if actual_total > int(budget["maximumOwnLayerBytes"]):
        raise ValueError("capture_actual_corpus_budget_exceeded")
    for name, payload in sorted(source_bytes_by_digest.items()):
        (public_root / name).write_bytes(payload)
    manifest: dict[str, Any] = {
        "schemaVersion": 2,
        "manifestVersion": "closy.capture_reconstruction.observable_manifest.v2",
        "protocolId": protocol["protocolId"],
        "protocolDigest": protocol["protocolDigest"],
        "partition": partition,
        "frozenSourceCommit": frozen_source_commit,
        "frozenSourceTree": frozen_source_tree,
        "sessionCount": len(public_rows),
        "sourceReferenceCount": source_count,
        "uniqueSourceFileCount": len(source_bytes_by_digest),
        "retainedBytes": sum(len(value) for value in source_bytes_by_digest.values()),
        "plannedMaximumBytes": planned_maximum,
        "contentAddressedDeduplication": True,
        "sessions": public_rows,
    }
    manifest["observableManifestDigest"] = canonical_digest(manifest)
    commitments: dict[str, Any] = {
        "schemaVersion": 2,
        "commitmentVersion": "closy.capture_reconstruction.truth_commitments.v2",
        "protocolDigest": protocol["protocolDigest"],
        "partition": partition,
        "sessionCount": len(commitment_rows),
        "rows": commitment_rows,
    }
    commitments["commitmentManifestDigest"] = canonical_digest(commitments)
    write_json(public_root.parent / f"{partition}_observable_manifest.json", manifest)
    write_json(public_root.parent / f"{partition}_truth_commitments.json", commitments)
    return {
        "manifest": manifest,
        "commitments": commitments,
        "evaluatorRoot": evaluator_root,
        "sourceFiles": source_bytes_by_digest,
    }


def validate_observable_manifest(root: Path, manifest: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    sessions = manifest.get("sessions")
    if not isinstance(sessions, list) or len(sessions) != int(manifest.get("sessionCount", -1)):
        return ["observable_session_denominator_invalid"]
    identities: set[str] = set()
    files: set[str] = set()
    for session in sessions:
        if set(session) - PUBLIC_SESSION_FIELDS:
            failures.append("observable_forbidden_session_field")
        identity = str(session.get("sessionId", ""))
        if not identity or identity in identities:
            failures.append("observable_session_identity_invalid")
        identities.add(identity)
        if not HEX256.fullmatch(str(session.get("truthCommitment", ""))):
            failures.append("observable_truth_commitment_format_invalid")
        sources = session.get("sources")
        if not isinstance(sources, list) or len(sources) != int(
            session.get("expectedSourceCount", -1)
        ):
            failures.append("observable_source_denominator_invalid")
            continue
        for source in sources:
            if set(source) - PUBLIC_SOURCE_FIELDS:
                failures.append("observable_forbidden_source_field")
            if source.get("kind") not in {"still", "video"}:
                failures.append("observable_source_kind_invalid")
            name = str(source.get("contentAddressedName", ""))
            if (
                not name
                or name != Path(name).name
                or "/" in name
                or "\\" in name
                or not HEX256.fullmatch(str(source.get("sourceSha256", "")))
            ):
                failures.append("observable_source_name_or_digest_format_invalid")
                continue
            path = root / name
            if not path.is_file() or sha256_bytes(path.read_bytes()) != source.get("sourceSha256"):
                failures.append("observable_source_digest_invalid")
                continue
            files.add(name)
            payload = path.read_bytes()
            if source.get("kind") == "video":
                decoded = decode_mjpeg_avi(payload)
                if len(decoded.frames) != int(source.get("decodedFrameCount", -1)):
                    failures.append("observable_video_frame_denominator_invalid")
                if len({frame.pixelSha256 for frame in decoded.frames}) != len(decoded.frames):
                    failures.append("observable_video_frames_not_distinct")
            else:
                try:
                    with Image.open(io.BytesIO(payload)) as image:
                        image.load()
                        width, height = image.size
                except OSError:
                    failures.append("observable_still_decode_failed")
                    continue
                if min(width, height) < 256:
                    failures.append("observable_still_resolution_invalid")
    if len(files) != int(manifest.get("uniqueSourceFileCount", -1)):
        failures.append("observable_unique_file_denominator_invalid")
    actual_files = {path.name for path in root.iterdir() if path.is_file()}
    if actual_files != files:
        failures.append("observable_source_inventory_mismatch")
    if manifest.get("observableManifestDigest") != canonical_digest(
        manifest, "observableManifestDigest"
    ):
        failures.append("observable_manifest_digest_invalid")
    return sorted(set(failures))


def corpus_denominators(manifest: dict[str, Any]) -> dict[str, Any]:
    sessions = manifest["sessions"]
    return {
        "sessions": len(sessions),
        "modeCounts": dict(sorted(Counter(row["mode"] for row in sessions).items())),
        "familyCounts": dict(sorted(Counter(row["family"] for row in sessions).items())),
        "modeFamilyCounts": {
            f"{mode}:{family}": count
            for (mode, family), count in sorted(
                Counter((row["mode"], row["family"]) for row in sessions).items()
            )
        },
    }


def _generate_session(
    session: dict[str, Any],
    protocol: dict[str, Any],
    *,
    frozen_source_commit: str,
    hidden_seed: str,
) -> tuple[dict[str, Any], dict[str, Any], list[tuple[str, bytes]]]:
    renderer = render_in_model if session["stratum"] == "in_model" else render_cross_generator
    hidden_nonce = int(hidden_seed[:16], 16)
    mode = str(session["mode"])
    observation_count = int(session["expectedSourceCount"])
    sources: list[tuple[str, bytes]] = []
    truth_observations: list[dict[str, Any]] = []
    public_sources: list[dict[str, Any]] = []
    if mode == "D":
        rendered_frames = [
            renderer(session, hidden_nonce=hidden_nonce, frame_index=index) for index in range(24)
        ]
        avi = encode_mjpeg_avi(
            rendered_frames[0].width,
            rendered_frames[0].height,
            [row.rgba for row in rendered_frames],
            jpeg_quality=int(protocol["artifactBudget"]["videoJpegQuality"]),
        )
        digest = sha256_bytes(avi)
        sources.append(("avi", avi))
        public_sources.append(
            {
                "sourceId": f"{session['sessionId']}-video",
                "kind": "video",
                "contentAddressedName": f"{digest}.avi",
                "sourceSha256": digest,
                "container": "RIFF_AVI",
                "codec": "MJPG",
                "width": rendered_frames[0].width,
                "height": rendered_frames[0].height,
                "decodedFrameCount": 24,
                "framesPerSecond": 12,
            }
        )
        truth_observations = [
            _truth_observation(row, index) for index, row in enumerate(rendered_frames)
        ]
    else:
        for source_index in range(observation_count):
            still = renderer(session, hidden_nonce=hidden_nonce, view_index=source_index)
            suffix, payload = _encode_still(still, hidden_nonce + source_index)
            digest = sha256_bytes(payload)
            sources.append((suffix, payload))
            public_sources.append(
                {
                    "sourceId": f"{session['sessionId']}-view-{source_index}",
                    "kind": "still",
                    "contentAddressedName": f"{digest}.{suffix}",
                    "sourceSha256": digest,
                    "codec": suffix.upper(),
                    "width": still.width,
                    "height": still.height,
                    "coarseCaptureRole": _coarse_role(mode, source_index),
                    "weakView": mode == "C" and source_index == session["weakOrMissingViewIndex"],
                }
            )
            truth_observations.append(_truth_observation(still, source_index))
    public_row = {
        "sessionId": session["sessionId"],
        "partition": session["partition"],
        "mode": mode,
        "family": session["family"],
        "declaredCalibrationTargetType": "rendered_0.20m_checker_or_diamond",
        "expectedSourceCount": observation_count,
        "expectedVideoFrames": session["expectedVideoFrames"],
        "sources": public_sources,
        "allowedFieldsOnly": True,
        "truthWithheld": True,
    }
    truth_row: dict[str, Any] = {
        "schemaVersion": 2,
        "truthVersion": "closy.capture_reconstruction.synthetic_truth.v2",
        "sessionId": session["sessionId"],
        "partition": session["partition"],
        "mode": mode,
        "family": session["family"],
        "stratum": session["stratum"],
        "producerIdentity": f"{session['stratum']}_renderer_v2",
        "seed": hidden_seed,
        "observations": truth_observations,
        "targetHypotheses": (
            [
                {"rank": 1, "kind": "symmetric_hidden_back"},
                {"rank": 2, "kind": "asymmetric_hidden_back"},
                {"rank": 3, "kind": "pleated_hidden_back"},
            ]
            if mode == "E"
            else []
        ),
        "frozenSourceCommit": frozen_source_commit,
    }
    truth_row["truthDigest"] = canonical_digest(truth_row)
    return public_row, truth_row, sources


def build_development_seed_authority(protocol: dict[str, Any]) -> dict[str, str]:
    return {
        str(row["sessionId"]): sha256_bytes(
            f"development-only:{protocol['protocolDigest']}:{row['sessionId']}".encode()
        )
        for row in protocol["sessionPlan"]
        if row["partition"] == "development"
    }


def create_locked_seed_authority(protocol: dict[str, Any]) -> dict[str, str]:
    """Create single-use secrets after source/evaluator freeze; never persist this in Git."""
    return {
        str(row["sessionId"]): secrets.token_hex(32)
        for row in protocol["sessionPlan"]
        if row["partition"] == "locked"
    }


def _truth_observation(rendered: RenderedObservation, index: int) -> dict[str, Any]:
    garment = rendered.masks["garment"]
    indexes = [position for position, value in enumerate(garment) if value]
    mean_rgb = [
        round(
            sum(rendered.rgba[position * 4 + channel] for position in indexes)
            / max(1, len(indexes)),
            8,
        )
        for channel in range(3)
    ]
    return {
        "observationIndex": index,
        "width": rendered.width,
        "height": rendered.height,
        "maskRuns": {name: mask_runs(mask) for name, mask in sorted(rendered.masks.items())},
        "landmarks": {name: list(value) for name, value in sorted(rendered.landmarks.items())},
        "camera": rendered.camera,
        "bodyPose": rendered.body_pose,
        "targetParameters": rendered.target_parameters,
        "frameState": rendered.frame_state,
        "visibleGarmentMeanRgb": mean_rgb,
    }


def _encode_still(rendered: RenderedObservation, nonce: int) -> tuple[str, bytes]:
    image = Image.frombytes("RGBA", (rendered.width, rendered.height), rendered.rgba)
    output = io.BytesIO()
    if nonce % 3 == 0:
        image.convert("RGB").save(
            output, format="JPEG", quality=82, subsampling=2, progressive=False
        )
        return "jpg", output.getvalue()
    image.save(output, format="PNG", compress_level=7, optimize=False)
    return "png", output.getvalue()


def _coarse_role(mode: str, index: int) -> str:
    if mode == "A":
        return "flat_or_hung"
    if mode == "B":
        return "worn"
    if mode == "C":
        return ("front", "side", "weak_rear")[index]
    if mode == "E":
        return "weak_single_view"
    return "dynamic_worn"
