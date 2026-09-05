# Manual provider binding V2 development

Status: **pass**. Baseline: 99/99 rows pass; 0 fail. This is exposed development only.

Rest max: 5.8095877142487886e-08 m; maximum per-shell P95: 4.2712688953318324e-08 m.
Motion max: 0.01608670800963261 m; P95 max: 0.0002271603414312708 m.
UV-edge max: 0.0003243232842949578 m (not physical seam gap).

| Source | Build 1 | Old rest max m | New rest max m |
|---|---|---:|---:|
| manual-skirt-01 | pass | 0.001984105287501984 | 3.0381993199540006e-08 |
| manual-skirt-02 | pass | 0.0019835583020519575 | 3.6596623801522346e-08 |
| manual-skirt-03 | pass | 0.002109253669708526 | 3.7606942498575824e-08 |
| manual-sleeveless-01 | pass | 0.01077327957737206 | 5.4581281682662046e-08 |
| manual-sleeveless-02 | pass | 0.006544922903341988 | 5.7401333159096434e-08 |
| manual-sleeveless-03 | pass | 0.006718755545565315 | 5.707599992661127e-08 |
| manual-tshirt-01 | pass | 0.012207575117394617 | 5.513100387645856e-08 |
| manual-tshirt-02 | pass | 0.010265803505453829 | 5.581185747540117e-08 |
| manual-tshirt-03 | pass | 0.011882778092215463 | 5.8095877142487886e-08 |

## Separate Extra Cases

- extra-dimensions: pass (built).
- extra-density: pass (built).
- extra-ordering: pass (built).
- extra-seam-opening: pass (built).
- reject-hole: pass (rejected).
- reject-offset: pass (rejected).
- reject-seam-index: pass (rejected).

## Unit A Compatibility

- tshirt: unsupported; binding_v2_unsupported_uv_lattice.
- sleeveless_top: unsupported; binding_v2_unsupported_uv_lattice.
- simple_skirt: unsupported; binding_v2_unsupported_uv_lattice.

Other families are unsupported/not claimed. No global C3, canonical promotion, physical fabric, mobile, or scientific qualification follows.
