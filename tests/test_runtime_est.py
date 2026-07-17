"""Runtime-remaining estimator: EMA smoothing, math, near-zero cap."""

from pytest import approx

from solarmon.runtime_est import RuntimeEstimator


def test_estimate_math():
    est = RuntimeEstimator(window_s=600)
    est.update(500, 5)
    # 15.36 kWh * 0.8 usable * 50% SoC = 6.144 kWh; / 500 W = 12.288 h
    hours, capped = est.runtime_hours(50, 15.36, 0.8)
    assert not capped
    assert hours == approx(12.288, rel=1e-3)


def test_ema_smooths_spikes():
    est = RuntimeEstimator(window_s=600)
    est.update(500, 5)
    est.update(5000, 5)  # kettle turns on for one poll
    # One 5s poll at 10x load moves the EMA by <1% of the jump
    assert est.smoothed_w < 600


def test_ema_converges_to_new_level():
    est = RuntimeEstimator(window_s=600)
    est.update(500, 5)
    for _ in range(600):  # 50 minutes at the new level
        est.update(1000, 5)
    assert est.smoothed_w == approx(1000, rel=0.01)


def test_near_zero_draw_capped():
    est = RuntimeEstimator(window_s=600)
    est.update(10, 5)  # 10 W: basically nothing
    hours, capped = est.runtime_hours(90, 15.36, 0.8)
    assert capped and hours is None


def test_long_runtime_capped_at_24h():
    est = RuntimeEstimator(window_s=600)
    est.update(100, 5)
    hours, capped = est.runtime_hours(100, 15.36, 0.8)  # 122 h raw
    assert capped and hours == 24.0


def test_no_estimate_before_data():
    est = RuntimeEstimator()
    hours, capped = est.runtime_hours(50, 15.36, 0.8)
    assert hours is None and not capped
