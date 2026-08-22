# T-Shirt Pattern v1

Implementation 01 supports only `garmentClass: "tshirt"`.

## Parameters

Bounded controls include:

- `garment_body_length`
- `half_chest_width`
- `body_ease`
- `shoulder_width`
- `shoulder_slope`
- `neckline_width`
- `front_neckline_depth`
- `back_neckline_depth`
- `armhole_depth`
- `sleeve_length`
- `sleeve_opening_width`
- `sleeve_cap_height`
- `hem_allowance`
- `neckband_width`
- `neckband_length_ease_ratio`
- `target_panel_edge_length`

Out-of-range values fail before package generation.

## Panels

Stable panel IDs:

- `panel.front`
- `panel.back`
- `panel.sleeve.left`
- `panel.sleeve.right`
- `panel.neck_band`

Boundaries are closed CCW panel-space loops. Curved construction uses quadratic/cubic Bezier curves for necklines, armholes, and sleeve caps.

## Seams And Openings

Stable seams are generated for shoulders, sides, armholes, sleeve underarms, neck-band closure, and neck-band attachment. Required openings remain explicitly open:

- `opening.neck`
- `opening.cuff.left`
- `opening.cuff.right`
- `opening.hem`

Seam constraints are deterministic vertex-pair constraints derived from sampled boundary spans. The package now stores `simulation/rest_state.json` for the analytic assembly and `simulation/settled_state.json` plus `simulation/settle_diagnostics.json` for the deterministic CPU reference settle. The settled simulation mesh drives the render fallback through the same barycentric binding contract.
