from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RenderedObservation:
    width: int
    height: int
    rgba: bytes
    masks: dict[str, bytes]
    landmarks: dict[str, tuple[float, float]]
    camera: dict[str, float]
    body_pose: dict[str, float]
    target_parameters: dict[str, float]
    frame_state: dict[str, Any]


def mask_runs(mask: bytes) -> list[list[int]]:
    runs: list[list[int]] = []
    start: int | None = None
    for index, value in enumerate(mask):
        if value and start is None:
            start = index
        elif not value and start is not None:
            runs.append([start, index - start])
            start = None
    if start is not None:
        runs.append([start, len(mask) - start])
    return runs


def runs_to_mask(runs: list[list[int]], length: int) -> bytes:
    mask = bytearray(length)
    for row in runs:
        if len(row) != 2:
            raise ValueError("mask_run_invalid")
        start, count = int(row[0]), int(row[1])
        if start < 0 or count <= 0 or start + count > length:
            raise ValueError("mask_run_bounds_invalid")
        mask[start : start + count] = b"\xff" * count
    return bytes(mask)
