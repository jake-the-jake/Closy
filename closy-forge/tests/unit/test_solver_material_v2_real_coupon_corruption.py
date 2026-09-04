from __future__ import annotations

import pytest

from closy_forge.solver_material_v2.real_coupon import (
    HEADER,
    CouponParseError,
    empty_real_coupon_report,
    parse_real_coupon_csv,
)


def test_empty_authorised_coupon_report_is_truthfully_zero() -> None:
    report = empty_real_coupon_report()
    assert report["realCouponCount"] == 0
    assert report["calibrationState"] == "not_run"


@pytest.mark.parametrize(
    "payload,reason",
    [
        (b"wrong,header\n", "header"),
        (b"\xff\xfe", "encoding"),
        (b"coupon_id\x00", "nul"),
        (
            (",".join(HEADER) + "\na,warp_extension,0.3,0.2,0.001,1,nan,0.01,0.1\n").encode(),
            "non_finite",
        ),
        ((",".join(HEADER) + "\na,wrong,0.3,0.2,0.001,1,1,0.01,0.1\n").encode(), "family"),
        (
            (",".join(HEADER) + "\na,warp_extension,-0.3,0.2,0.001,1,1,0.01,0.1\n").encode(),
            "positive",
        ),
    ],
)
def test_corrupt_coupon_inputs_fail_closed(payload: bytes, reason: str) -> None:
    with pytest.raises(CouponParseError, match=reason):
        parse_real_coupon_csv(payload)
