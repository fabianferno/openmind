from agent.execution import safety


def test_all_clear_when_fresh():
    ok, checks = safety.all_clear()
    assert ok
    assert all(not c.tripped for c in checks)


def test_manual_breaker_round_trip():
    safety.trip_manual("test")
    ok, _ = safety.all_clear()
    assert not ok
    safety.reset_manual()
    ok2, _ = safety.all_clear()
    assert ok2


def test_slippage_check():
    assert safety.slippage_ok(0.4, 0.405)
    assert not safety.slippage_ok(0.4, 0.45)
    assert not safety.slippage_ok(0, 0.4)
