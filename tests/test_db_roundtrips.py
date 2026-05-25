from datetime import UTC, datetime

from agent.store import db


def test_market_upsert_and_get():
    with db.connect() as conn:
        mid = db.upsert_market(conn, {
            "venue": "test",
            "external_id": "m1",
            "question": "Q?",
            "category": "geopolitics",
            "end_date": "2030-01-01T00:00:00+00:00",
            "last_price_yes": 0.4,
            "volume_24h": 1234.0,
        })
        got = db.get_market(conn, mid)
    assert got and got["question"] == "Q?"
    assert got["volume_24h"] == 1234.0


def test_decision_roundtrip():
    with db.connect() as conn:
        mid = db.upsert_market(conn, {"venue": "t", "external_id": "m2", "question": "Q"})
        did = db.record_decision(conn, {
            "market_id": mid, "kind": "entry", "as_of": "2024-01-01T00:00:00+00:00",
            "prompt": "p", "search_used": [{"url": "u"}],
            "model_id": "x", "response_raw": "{}", "response_json": {"a": 1},
            "p_yes": 0.55, "confidence": 0.6, "action": "enter_yes",
            "input_tokens": 100, "output_tokens": 50, "cost_usd": 0.001,
        })
        row = conn.execute("SELECT * FROM decisions WHERE id = ?", (did,)).fetchone()
    assert row["p_yes"] == 0.55
    assert row["action"] == "enter_yes"
    assert row["cost_usd"] == 0.001


def test_position_open_close():
    with db.connect() as conn:
        mid = db.upsert_market(conn, {"venue": "t", "external_id": "m3", "question": "Q"})
        pid = db.open_position(conn, {
            "market_id": mid, "venue": "t", "side": "YES",
            "shares": 10.0, "entry_price": 0.4, "notional_in": 4.0,
        })
        db.close_position(
            conn, pid, exit_price=0.55, notional_out=5.5,
            exit_decision_id=None, venue_exit_order=None,
            p_yes_at_exit=0.55, fees=0.0,
        )
        row = conn.execute("SELECT * FROM positions WHERE id = ?", (pid,)).fetchone()
    assert row["status"] == "closed"
    # pnl = 5.5 - 4.0 - 0 = 1.5
    assert abs(row["pnl"] - 1.5) < 1e-6


def test_llm_usage_accumulates():
    with db.connect() as conn:
        db.add_llm_usage(conn, 100, 200, 0.001)
        db.add_llm_usage(conn, 50, 60, 0.0005)
        spent = db.llm_cost_today(conn)
    assert abs(spent - 0.0015) < 1e-9


def test_blocklist_substring_match():
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO blocklist (pattern, reason, added_at) VALUES (?, ?, ?)",
            ("forbidden", "test", datetime.now(UTC).isoformat()),
        )
        assert db.in_blocklist(conn, "this is a FORBIDDEN topic")
        assert not db.in_blocklist(conn, "this is fine")


def test_snapshot_at_or_before():
    with db.connect() as conn:
        mid = db.upsert_market(conn, {"venue": "t", "external_id": "snap", "question": "Q"})
        db.insert_snapshot(conn, {"market_id": mid, "as_of": "2024-01-01T00:00:00+00:00",
                                   "price_yes": 0.3})
        db.insert_snapshot(conn, {"market_id": mid, "as_of": "2024-02-01T00:00:00+00:00",
                                   "price_yes": 0.4})
        snap = db.snapshot_at_or_before(conn, mid, "2024-01-15T00:00:00+00:00")
    assert snap is not None
    assert abs(snap["price_yes"] - 0.3) < 1e-9
