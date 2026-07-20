import os, sys, importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

def test_format_dump_has_all_sections(tmp_path, monkeypatch):
    monkeypatch.setenv("MDB_DATA_DIR", str(tmp_path))
    import store; importlib.reload(store)
    store.append_comments([{"date": "2026-07-19", "uid": "telegram_crawler",
        "headline": "엔비디아 신고가", "text": "목표주가 상향", "tickers": {"s1": ["NVDA"]},
        "author": "@ch", "tg_link": "https://t.me/ch/1",
        "importanceScore": 9, "importanceTier": "high"}])
    store.write_prices("us", "2026-07-19", {"NVDA": {"name": "엔비디아", "daily_return": 3.1}})
    store.write_macro({"sp500": {"c": [100.0, 105.0], "prev_close": 100.0}})
    store.write_calendar([{"date": "2026-07-20", "time": "21:30", "event": "CPI"}],
                         [{"date": "2026-07-21", "symbol": "NVDA"}])
    import digest; importlib.reload(digest); digest.store = store
    out = digest.format_dump(digest.fetch_digest_data("2026-07-19"))
    assert "📈 주가 등락" in out and "엔비디아" in out
    assert "📰 뉴스·레포트 원천" in out and "엔비디아 신고가" in out
    assert "🌐 매크로" in out and "🗓 캘린더" in out and "CPI" in out

def test_dump_empty_is_graceful(tmp_path, monkeypatch):
    monkeypatch.setenv("MDB_DATA_DIR", str(tmp_path / "e"))
    import store; importlib.reload(store)
    import digest; importlib.reload(digest); digest.store = store
    out = digest.format_dump(digest.fetch_digest_data("2026-07-19"))
    assert "데이터 없음" in out
