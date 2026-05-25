from datetime import UTC, datetime, timedelta

from agent.strategy import filters


def base_market(**overrides):
    m = {
        "category": "geopolitics",
        "volume_24h": 50_000,
        "book_depth_5c": 1500,
        "last_price_yes": 0.4,
        "end_date": (datetime.now(UTC) + timedelta(days=10)).isoformat(),
    }
    m.update(overrides)
    return m


def test_passes_all_happy():
    assert filters.passes_all(base_market()).accepted


def test_rejects_low_volume():
    assert not filters.passes_all(base_market(volume_24h=100)).accepted


def test_rejects_extreme_price():
    assert not filters.passes_all(base_market(last_price_yes=0.99)).accepted
    assert not filters.passes_all(base_market(last_price_yes=0.01)).accepted


def test_rejects_short_time_to_resolution():
    short = (datetime.now(UTC) + timedelta(hours=12)).isoformat()
    assert not filters.passes_all(base_market(end_date=short)).accepted


def test_rejects_long_time_to_resolution():
    longt = (datetime.now(UTC) + timedelta(days=120)).isoformat()
    assert not filters.passes_all(base_market(end_date=longt)).accepted


def test_depth_unknown_defers_not_rejects():
    res = filters.depth_ok({"book_depth_5c": None})
    assert res.accepted


def test_category_filter_matches_substring():
    # 'world' should match 'world-events'
    m = base_market(category="world-events")
    assert filters.category_ok(m).accepted
