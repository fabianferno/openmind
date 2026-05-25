import math

from agent.strategy import calibration


def test_brier_score_basic():
    # perfect forecaster: p=1 when y=1, p=0 when y=0
    preds = [(1.0, 1.0), (0.0, 0.0)]
    assert calibration.brier_score(preds) == 0.0


def test_brier_score_average():
    preds = [(0.5, 1.0), (0.5, 0.0)]
    # (0.5-1)^2 + (0.5-0)^2 = 0.25 + 0.25 → mean = 0.25
    assert math.isclose(calibration.brier_score(preds), 0.25, abs_tol=1e-9)


def test_brier_empty_returns_none():
    assert calibration.brier_score([]) is None


def test_ece_perfectly_calibrated():
    # bins of size 10 — pure-fraction examples
    preds = [(0.1, 0.0)] * 9 + [(0.1, 1.0)] * 1   # 10% predicted, 10% actual
    preds += [(0.9, 1.0)] * 9 + [(0.9, 0.0)] * 1  # 90% predicted, 90% actual
    e = calibration.ece(preds)
    assert e is not None
    assert e < 0.05


def test_multiplier_does_not_raise_with_few_bets():
    assert calibration._next_multiplier(0.5, n=5, brier=0.1) == 0.5


def test_multiplier_raises_with_good_brier():
    assert calibration._next_multiplier(0.5, n=30, brier=0.1) > 0.5


def test_multiplier_decays_on_bad_brier():
    assert calibration._next_multiplier(0.9, n=30, brier=0.3) < 0.9
