from __future__ import annotations

import hashlib
import json
import os
import socket
import struct
import zlib
from pathlib import Path

INPUT = Path("/inputs")
OUTPUT = Path("/outputs")
ROUTE = os.environ.get("ROUTE_ID", "")


def _write(name: str, value: object) -> None:
    path = OUTPUT / name
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _blocked_read(path: str) -> bool:
    try:
        Path(path).read_bytes()
    except (OSError, PermissionError):
        return True
    return False


def _blocked_write(path: str) -> bool:
    try:
        Path(path).write_bytes(b"forbidden")
    except (OSError, PermissionError):
        return True
    return False


def _network_blocked() -> bool:
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=0.25):
            return False
    except OSError:
        return True


def _security_probe() -> dict[str, object]:
    return {
        "repositoryReadBlocked": _blocked_read("/workspace/.git/HEAD"),
        "evaluatorReadBlocked": _blocked_read("/evaluator/targets.json"),
        "privateReadBlocked": _blocked_read("/private/user-source.png"),
        "hostHomeReadBlocked": _blocked_read("/home/runner/.ssh/id_rsa"),
        "dockerSocketReadBlocked": _blocked_read("/var/run/docker.sock"),
        "outsideOutputWriteBlocked": _blocked_write("/forbidden-write"),
        "networkBlocked": _network_blocked(),
        "secretEnvironmentAbsent": all(
            os.environ.get(name) is None
            for name in ("GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "SUPABASE_SERVICE_ROLE_KEY")
        ),
        "undeclaredEnvironmentAbsent": set(os.environ) <= {
            "LANG",
            "LC_ALL",
            "PATH",
            "PYTHONHASHSEED",
            "ROUTE_ID",
        },
    }


def _decode_png(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("png_signature_invalid")
    offset = 8
    width = height = 0
    compressed = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, colour_type = struct.unpack(">IIBB", payload[:10])
            if bit_depth != 8 or colour_type != 6:
                raise ValueError("png_rgba8_required")
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    raw = zlib.decompress(bytes(compressed))
    stride = width * 4
    rows: list[bytearray] = []
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        scanline = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        previous = rows[-1] if rows else bytearray(stride)
        for index in range(stride):
            left = scanline[index - 4] if index >= 4 else 0
            above = previous[index]
            upper_left = previous[index - 4] if index >= 4 else 0
            if filter_type == 1:
                scanline[index] = (scanline[index] + left) & 255
            elif filter_type == 2:
                scanline[index] = (scanline[index] + above) & 255
            elif filter_type == 3:
                scanline[index] = (scanline[index] + ((left + above) // 2)) & 255
            elif filter_type == 4:
                prediction = left + above - upper_left
                distances = (abs(prediction - left), abs(prediction - above), abs(prediction - upper_left))
                predictor = (left, above, upper_left)[distances.index(min(distances))]
                scanline[index] = (scanline[index] + predictor) & 255
            elif filter_type != 0:
                raise ValueError("png_filter_invalid")
        rows.append(scanline)
    return width, height, b"".join(rows)


def _features(path: Path) -> dict[str, float]:
    width, height, rgba = _decode_png(path)
    occupied_rows: list[list[int]] = []
    for y in range(height):
        occupied = [x for x in range(width) if rgba[(y * width + x) * 4 + 3] > 0]
        if occupied:
            occupied_rows.append(occupied)
    if not occupied_rows:
        raise ValueError("pixel_mask_empty")
    row_widths = [row[-1] - row[0] + 1 for row in occupied_rows]
    torso = row_widths[len(row_widths) // 2 :]
    return {
        "body_height": len(occupied_rows) / height,
        "torso_width": sorted(torso)[len(torso) // 2] / width,
        "shoulder_width": max(row_widths) / width,
        "sleeve_extent": (max(row_widths) - sorted(torso)[len(torso) // 2]) / width,
    }


def _pixel_prediction() -> tuple[dict[str, float], dict[str, object]]:
    front_path = INPUT / "front.png"
    rear_path = INPUT / "rear.png"
    front = _features(front_path)
    rear = _features(rear_path)
    features = {name: (front[name] + rear[name]) / 2.0 for name in front}
    if ROUTE == "pixel_mask_landmark_optimiser":
        prediction = {
            "garment_body_length": features["body_height"] * 0.98,
            "half_chest_width": features["torso_width"] * 0.54,
            "shoulder_width": features["shoulder_width"] * 0.73,
            "sleeve_length": features["sleeve_extent"] * 0.80,
        }
        model_digest = None
    else:
        model = json.loads((INPUT / "model.json").read_text(encoding="utf-8"))
        prediction = {}
        for target, row in model["weights"].items():
            prediction[target] = row["intercept"] + row["slope"] * features[row["feature"]]
        model_digest = model["modelDigest"]
    lineage = {
        "frontSha256": hashlib.sha256(front_path.read_bytes()).hexdigest(),
        "rearSha256": hashlib.sha256(rear_path.read_bytes()).hexdigest(),
        "features": features,
        "modelDigest": model_digest,
        "routeId": ROUTE,
        "targetOrEvaluatorMounted": False,
    }
    return prediction, lineage


def main() -> None:
    security = _security_probe()
    if not all(security.values()):
        raise RuntimeError("container_security_probe_failed")
    if ROUTE == "generic_canary":
        canary = (INPUT / "canary.bin").read_bytes()
        _write(
            "probe.json",
            {
                "routeId": ROUTE,
                "inputSha256": hashlib.sha256(canary).hexdigest(),
                "security": security,
                "uid": os.getuid(),
                "gid": os.getgid(),
                "fsyncCompleted": True,
            },
        )
        return
    if ROUTE in {"metadata_category_control", "no_pixel_template_prior"}:
        prediction = {
            "garment_body_length": 0.58,
            "half_chest_width": 0.26,
            "shoulder_width": 0.67,
            "sleeve_length": 0.21,
        }
        lineage = {"routeId": ROUTE, "pixelsConsumed": False, "targetOrEvaluatorMounted": False}
    elif ROUTE in {"pixel_mask_landmark_optimiser", "pixel_learned_structured_tshirt"}:
        prediction, lineage = _pixel_prediction()
        lineage["pixelsConsumed"] = True
    else:
        raise ValueError("route_unknown")
    _write("prediction.json", {"routeId": ROUTE, "parameters": prediction})
    _write("lineage.json", {**lineage, "security": security})


if __name__ == "__main__":
    main()
