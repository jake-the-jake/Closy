# Forge Numeric Canonicalization v1

Forge canonical packages use bounded decimal quantization at authored execution boundaries so
supported Python minors and operating systems produce identical bytes without changing acceptance
thresholds.

## Policy

- General family vertical-slice solver positions are quantized to six decimal places after each
  bounded solver projection stage.
- T-shirt fitting, material motion suites, C3 state reconstruction, and full-solver verification
  use nine decimal places to retain the precision required by their tighter metric gates.
- Diagnostics derived from a canonicalized solver run are recursively quantized to the same number
  of decimal places. Counts, identifiers, booleans, and hashes are unchanged.
- Float reductions that contribute to canonical evidence use `math.fsum` where order-sensitive
  accumulation could otherwise vary across Python 3.11 and 3.12.
- Signed zero is normalized by the existing geometry canonicalization path. Non-finite values remain
  invalid and are never converted into accepted canonical values.

This policy does not widen geometry, seam, collision, fidelity, or physical-quality thresholds. A
future change to the quantization boundary or precision requires a new policy version, deterministic
cross-minor evidence, and an explicit golden transition.

## Golden transition

The v1 transition intentionally changes canonical package digests because solver positions and
their dependent reports are now stable across Python minors. GitHub Actions run `33135213672`
proved identical Python 3.11/3.12 and Ubuntu/Windows family inventories before these golden values
were accepted.

| Family | Previous digest | Canonicalization v1 digest |
| --- | --- | --- |
| T-shirt | `de016b7d0409356db24ddcf818ea57dde0d708aa82c6b4436b690ee1d2ff1a5b` | `617200c174cb583df0cbcf59c113b3b853a4668b89416cbdca3b6bab521d56a1` |
| Sleeveless | `c5a5f3b1b59a0f96b821e68e9f7aaefa548c0fc9df72bef8704e517fb9a240d3` | `6cae3ba73991f4355db6a8045747128f64b8d6bafaf50616055f16cfd966053a` |
| Long-sleeved | `b239341db917fa0a0785a9123b75db0d2b16318ccf06005619093e85c7bc09a3` | `fea9d2bb9fad5216ffe92ea681756d96b8c4be133492d5e036dc55cbd59ee2b1` |
| Simple skirt | `b264f8530dd7383a7bafd8d48cab68b0ec433f2936f9133c7e0907bbcece65f5` | `ea66fa66a611d22c7bfff44dde87681dcddefe02fbd3441a6fcd4703eeac0898` |
| Simple trousers | `e712800bc59b8b3a8ed12028fffef0d29afae108f556b8b95c24e3939a894c4a` | `9d91b70a9da016d5baf63eb26f57479192ae50040b45ef308632e8b285d05ac6` |
| Simple dress | `2dbd97fe819a334c287deff0bb699bc895804789df43dd219f5cc52b2cb71496` | `1ca8d89ee5629ebffb9c252724722b8c1418ed0966e48c3b7270024a08de3f40` |
| Button shirt | `56e18ef3f9a98b8ccc5bf984ecf7c64bb3ea5960108e2b4fd53108cbafa3f7cf` | `f561119ddeddf11bc3722db09da7893e614bb235907b884aee02356bfb269ca0` |
| Jacket outerwear | `41b8b9a8569ba272d136dcc0f7623a9739ab8baee0bf70d121914c55846bec98` | `fe66f9a5b78a7829169c9ce3b479c671e97b99f7dddf0fcb8da99994082358c7` |
| Layered asymmetric | `1baef98b30384c63d71dd76dea7f25ca9922cbdc1b4b413d86b90841fba7ec2c` | `b8d211d347b1d74f6ff14a89ff81b150e8994a94fa07769081a1e3fedcc0faff` |

The same run retained package validation, byte-identical clean rebuilds, and the full canonical
inventory comparison. Its cumulative lane failed only because the old golden constants above had
not yet been transitioned; the corrected exact-head rerun is the acceptance authority.
