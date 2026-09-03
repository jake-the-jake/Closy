from closy_forge.capture_engineering_v1.corruption import run_corruption_suite


def test_capture_and_video_corruption_denominator_is_fixed_and_fail_closed() -> None:
    result = run_corruption_suite()
    assert result["attemptCount"] == 16
    assert result["passCount"] == 16
    assert result["allExpectedOutcomesObserved"] is True
