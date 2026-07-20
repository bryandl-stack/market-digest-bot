import os, sys, importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "crawlers"))

def test_load_trailing_scores_reads_store(tmp_path, monkeypatch):
    monkeypatch.setenv("MDB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_API_ID", "123")
    monkeypatch.setenv("TELEGRAM_API_HASH", "dummy")
    import store; importlib.reload(store)
    store.append_comments([{"date": "2026-07-18", "importanceScore": 5.0, "headline": "h"}])
    store.append_comments([{"date": "2026-07-19", "importanceScore": 9.0, "headline": "h2"}])
    import crawl_telegram; importlib.reload(crawl_telegram)
    crawl_telegram.store = store  # 동일 DATA_DIR 보장
    scores = crawl_telegram.load_trailing_scores("2026-07-19", days=7)
    assert scores == [9.0, 5.0]
    assert 9.0 in scores  # date_str 당일 저장분도 trailing pool에 포함되어야 함(원본과 동일 동작)
