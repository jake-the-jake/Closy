from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import read_binding
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.strict_c3_confirmation_v5.candidate import deform_candidate_simulation
from closy_forge.strict_c3_confirmation_v5.evaluator import vertex_digest
from closy_forge.strict_c3_confirmation_v5.protocol import UNIT_F_PACKAGE


def main() -> int:
    parser = argparse.ArgumentParser(description="Repeat Unit N reconstruction in a fresh process.")
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    payload = _mapping(json.loads(sys.stdin.read()))
    poses = payload.get("poses")
    if not isinstance(poses, list):
        raise ValueError("unit_n_repeat_pose_inventory_invalid")
    package = args.root.resolve() / UNIT_F_PACKAGE
    simulation = read_glb_meshset(package / "simulation/settled_mesh.glb")
    binding = read_binding(package / "binding/sim_to_render.bin")
    digests = [
        vertex_digest(
            reconstruct_vertices(deform_candidate_simulation(simulation, _mapping(pose)), binding)
        )
        for pose in poses
    ]
    sys.stdout.write(canonical_dumps({"digests": digests}))
    return 0


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


if __name__ == "__main__":
    raise SystemExit(main())
