import os, importlib

def _fresh_store(tmp_path):
    os.environ["MDB_DATA_DIR"] = str(tmp_path)
    import store
    importlib.reload(store)
    return store

def test_comments_roundtrip_strips_terms_and_serializes_timestamp(tmp_path):
    from datetime import datetime, timezone
    store = _fresh_store(tmp_path)
    n = store.append_comments([{
        "date": "2026-07-19", "headline": "h1", "tg_link": "https://t.me/a/1",
        "timestamp": datetime(2026, 7, 19, tzinfo=timezone.utc), "_terms": {"x"},
    }])
    assert n == 1
    got = store.read_comments(["2026-07-19"])
    assert len(got) == 1
    assert "_terms" not in got[0]
    assert got[0]["timestamp"] == "2026-07-19T00:00:00+00:00"
    assert store.existing_links("2026-07-19") == {"https://t.me/a/1"}
    assert store.existing_headlines("2026-07-19") == ["h1"]

def test_read_comments_missing_date_is_empty(tmp_path):
    store = _fresh_store(tmp_path)
    assert store.read_comments(["2000-01-01"]) == []

def test_prices_latest_on_or_before(tmp_path):
    store = _fresh_store(tmp_path)
    store.write_prices("us", "2026-07-17", {"AAPL": {"name": "Apple", "daily_return": 1.0}})
    store.write_prices("us", "2026-07-18", {"AAPL": {"name": "Apple", "daily_return": 2.0}})
    d, rows = store.read_latest_prices("us", "2026-07-19")
    assert d == "2026-07-18" and rows["AAPL"]["daily_return"] == 2.0
    d2, _ = store.read_latest_prices("us", "2026-07-17")
    assert d2 == "2026-07-17"
    assert store.read_latest_prices("kr", "2026-07-19") == (None, {})

def test_macro_and_calendar_roundtrip(tmp_path):
    store = _fresh_store(tmp_path)
    store.write_macro({"sp500": {"c": [1.0, 2.0], "prev_close": 1.5}})
    assert store.read_macro()["sp500"]["prev_close"] == 1.5
    store.write_calendar([{"date": "2026-07-20", "event": "CPI"}], [{"date": "2026-07-21", "symbol": "AAPL"}])
    cal = store.read_calendar()
    assert cal["economic"][0]["event"] == "CPI" and cal["earnings"][0]["symbol"] == "AAPL"
    # 빈 상태 기본값
    import importlib
    os.environ["MDB_DATA_DIR"] = str(tmp_path / "empty")
    importlib.reload(store)
    assert store.read_macro() == {}
    assert store.read_calendar() == {"economic": [], "earnings": []}
