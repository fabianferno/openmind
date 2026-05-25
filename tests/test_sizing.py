import math

from agent.strategy import sizing


def test_kelly_no_edge_returns_zero():
    assert sizing.kelly_fraction(0.5, 0.5) == 0.0
    assert sizing.kelly_fraction(0.3, 0.5) == 0.0


def test_kelly_positive_edge():
    # Agent thinks 0.6, market is 0.5 → positive Kelly fraction
    f = sizing.kelly_fraction(0.6, 0.5)
    assert f > 0
    # Closed-form: b = 1, f = (0.6*1 - 0.4)/1 = 0.2
    assert math.isclose(f, 0.2, abs_tol=1e-6)


def test_size_position_no_edge():
    s = sizing.size_position(p_agent=0.5, p_market=0.5, bankroll=50, per_market_cap=2)
    assert s.usd == 0.0
    assert s.reason == "no_edge"


def test_size_position_capped_by_per_market():
    s = sizing.size_position(
        p_agent=0.9, p_market=0.5, bankroll=10_000, per_market_cap=2.0,
        calibration_mul=1.0,
    )
    # Without caps Kelly would be huge; per-market cap binds.
    assert s.usd == 2.0 * 1.0
    assert s.side == "YES"


def test_size_position_no_side_inverts_for_negative_edge():
    s = sizing.size_position(p_agent=0.3, p_market=0.5, bankroll=10_000,
                              per_market_cap=2.0, calibration_mul=1.0)
    assert s.side == "NO"
    assert s.usd > 0


def test_calibration_multiplier_scales_size_linearly():
    high = sizing.size_position(p_agent=0.9, p_market=0.5, bankroll=10_000,
                                 per_market_cap=10.0, calibration_mul=1.0).usd
    low = sizing.size_position(p_agent=0.9, p_market=0.5, bankroll=10_000,
                                per_market_cap=10.0, calibration_mul=0.5).usd
    assert math.isclose(low, high * 0.5, abs_tol=1e-6)
