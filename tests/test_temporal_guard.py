from datetime import UTC, datetime

from agent.reasoning import temporal_guard


def make_hit(date: str | None) -> dict:
    return {"title": "t", "url": f"http://x/{date}", "content": "c", "published_date": date}


def test_drops_post_dated():
    as_of = datetime(2024, 6, 1, tzinfo=UTC)
    results = [
        make_hit("2024-05-01"),     # ok
        make_hit("2024-07-01"),     # too late
        make_hit("2024-06-01"),     # boundary — included
    ]
    kept = temporal_guard.filter_results(results, as_of)
    urls = {r["url"] for r in kept}
    assert "http://x/2024-05-01" in urls
    assert "http://x/2024-06-01" in urls
    assert "http://x/2024-07-01" not in urls


def test_drops_undated_by_default():
    as_of = datetime(2024, 6, 1, tzinfo=UTC)
    kept = temporal_guard.filter_results([make_hit(None)], as_of)
    assert kept == []


def test_allow_undated_optional():
    as_of = datetime(2024, 6, 1, tzinfo=UTC)
    kept = temporal_guard.filter_results([make_hit(None)], as_of, allow_undated=True)
    assert len(kept) == 1


def test_parse_iso_tolerant():
    assert temporal_guard.parse_iso("2024-06-01T00:00:00Z") is not None
    assert temporal_guard.parse_iso("2024-06-01") is not None
    assert temporal_guard.parse_iso(None) is None
    assert temporal_guard.parse_iso("garbage") is None
