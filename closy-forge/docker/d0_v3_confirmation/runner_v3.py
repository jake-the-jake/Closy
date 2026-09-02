from __future__ import annotations

import importlib.util
import os
from collections import Counter
from pathlib import Path
from types import ModuleType

PUBLIC_ROUTE = os.environ.get("ROUTE_ID", "")
ROUTE_ALIASES = {
    "metadata_category_control_v3": "metadata_category_control",
    "no_pixel_template_prior_v3": "no_pixel_template_prior",
    "pixel_mask_landmark_optimizer_v3": "pixel_mask_landmark_optimiser",
    "pixel_learned_structured_tshirt_v3": "pixel_learned_structured_tshirt",
}


def _load_base() -> ModuleType:
    os.environ["ROUTE_ID"] = ROUTE_ALIASES.get(PUBLIC_ROUTE, PUBLIC_ROUTE)
    specification = importlib.util.spec_from_file_location(
        "closy_d0_v3_base_runner", "/app/base_runner.py"
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("base_runner_import_failed")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _appearance(module: ModuleType) -> dict[str, object]:
    if PUBLIC_ROUTE not in {
        "pixel_mask_landmark_optimizer_v3",
        "pixel_learned_structured_tshirt_v3",
    }:
        return _default_appearance()
    width, height, rgba = module._decode_png(Path("/inputs/front.png"))
    colours: Counter[tuple[int, int, int]] = Counter()
    for offset in range(0, len(rgba), 4):
        if rgba[offset + 3] > 0:
            colours[tuple(rgba[offset : offset + 3])] += 1
    ordered = colours.most_common(2)
    result = _default_appearance()
    if ordered:
        result["baseColorSrgb"] = list(ordered[0][0])
    if len(ordered) > 1:
        result["logoColorSrgb"] = list(ordered[1][0])
        result["logoShape"] = "bar"
        result["logoScaleNormalized"] = 0.1
    result["decodedImageSize"] = [width, height]
    return result


def _default_appearance() -> dict[str, object]:
    return {
        "baseColorSrgb": [92, 104, 119],
        "logoCenterNormalized": [0.5, 0.5],
        "logoColorSrgb": [238, 231, 214],
        "logoScaleNormalized": 0.1,
        "logoShape": "none",
        "neckShape": "crew",
        "roughness": 0.72,
        "metalness": 0.0,
        "ambientOcclusion": 0.9,
    }


def main() -> None:
    module = _load_base()
    original_write = module._write

    def write(name: str, value: object) -> None:
        if isinstance(value, dict):
            value = dict(value)
            if name == "prediction.json":
                value["routeId"] = PUBLIC_ROUTE
                value["appearance"] = _appearance(module)
            elif name == "lineage.json":
                value["routeId"] = PUBLIC_ROUTE
        original_write(name, value)

    module._write = write
    module.main()


if __name__ == "__main__":
    main()
