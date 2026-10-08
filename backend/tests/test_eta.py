"""Remaining-time estimates and the replay that measures them."""

import pytest

from app.services import eta
from conftest import load_script

analyze = load_script("analyze_job")


def test_each_method_needs_enough_evidence_before_answering():
    first = eta.Reading(0, 0.40, 100)
    assert eta.by_progress(first, eta.Reading(30, 0.401, 101)) is None  # too little progress and time
    assert eta.by_layers(first, eta.Reading(30, 0.41, 101), 486) is None
    assert eta.by_progress(first, eta.Reading(600, 0.50, 110)) == pytest.approx(600 * 0.5 / 0.10)
    assert eta.by_layers(first, eta.Reading(600, 0.50, 110), 486) == pytest.approx((486 - 110) * 600 / 10)
    assert eta.by_slicer(21627, 12000) == 9627 and eta.by_slicer(21627, 30000) == 0 and eta.by_slicer(None, 5) is None


def test_recent_window_follows_a_pace_that_changes():
    first = eta.Reading(0, 0.0, 0)
    window = eta.Reading(1000, 0.4, 10)  # 100 s per layer so far...
    now = eta.Reading(1600, 0.5, 30)  # ...then 30 s per layer
    assert eta.by_layers(first, now, 50) == pytest.approx(20 * 1600 / 30)
    assert eta.by_layers(first, now, 50, window=window) == pytest.approx(20 * 600 / 20)


def test_errors_use_only_the_moments_a_method_answered():
    result = eta.errors([(100.0, 120.0), (50.0, None), (10.0, 5.0)])
    assert result["moments"] == 2 and result["answered"] == pytest.approx(2 / 3)
    assert result["mean_abs_error_s"] == pytest.approx(12.5) and result["mean_signed_error_s"] == pytest.approx(7.5)
    assert eta.errors([(1.0, None)]) is None


def test_replay_ranks_the_methods_on_a_print_whose_progress_is_not_linear_in_time():
    # 100 layers of 30 s; the file's progress runs slowly at first and fast at the end.
    points = [(float(second), (second / 3000) ** 2, second // 30) for second in range(0, 3001)]
    result = analyze.replay(points, 3000.0, 100, 3600.0, 0.0, 60.0, 600.0)
    errors = result["errors"]
    assert errors["layers"]["mean_abs_error_s"] < errors["progress"]["mean_abs_error_s"]
    assert errors["layers"]["mean_abs_error_s"] < 120  # constant layers: close to exact
    assert errors["slicer"]["mean_signed_error_s"] == pytest.approx(600.0)  # the slicer said 3600, took 3000
