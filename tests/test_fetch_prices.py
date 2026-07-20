import os, sys, json, importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "crawlers"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

def test_build_ticker_list_from_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config"; cfg.mkdir()
    (cfg / "universe.json").write_text(json.dumps({
        "us": [{"id": "s1", "name": "반도체",
                "stocks": [{"ticker": "NVDA", "nameKr": "엔비디아"}]}]}), encoding="utf-8")
    monkeypatch.setenv("MDB_CONFIG_DIR", str(cfg))
    import config_loader; importlib.reload(config_loader)
    _n, t2n, tc = config_loader.load_universe(["us"])
    assert [tk for tk, c in tc.items() if c == "us"] == ["NVDA"]
    assert t2n["NVDA"] == "엔비디아"

def test_single_ticker_multiindex_download(tmp_path, monkeypatch):
    """단일 티커 시장: yfinance가 MultiIndex 컬럼 DataFrame을 반환해도 크래시 없이 저장."""
    import pandas as pd
    cfg = tmp_path / "config"; cfg.mkdir()
    (cfg / "universe.json").write_text(json.dumps({
        "kr": [{"id": "s1", "name": "반도체",
                "stocks": [{"ticker": "005930.KS", "nameKr": "삼성전자"}]}]}), encoding="utf-8")
    monkeypatch.setenv("MDB_CONFIG_DIR", str(cfg))
    monkeypatch.setenv("MDB_DATA_DIR", str(tmp_path / "data"))

    import config_loader; importlib.reload(config_loader)
    import store; importlib.reload(store)
    import fetch_prices; importlib.reload(fetch_prices)

    # yfinance 1.3.x 스타일 단일 티커 반환: MultiIndex (field, ticker)
    idx = pd.to_datetime(["2026-07-16", "2026-07-17", "2026-07-18"])
    cols = pd.MultiIndex.from_product([["Close", "Open"], ["005930.KS"]])
    raw = pd.DataFrame([[100, 99], [102, 101], [105, 104]], index=idx, columns=cols)

    monkeypatch.setattr(fetch_prices.yf, "download", lambda *a, **k: raw)
    monkeypatch.setattr(fetch_prices, "fetch_market_caps",
                        lambda tickers: ({}, {}, {}, {}))
    monkeypatch.setattr(fetch_prices, "get_fx_to_usd", lambda curs: {})

    fetch_prices.fetch_and_store("2026-07-18", "kr", is_today=False)

    _, rows = store.read_latest_prices("kr", "2026-07-18")
    assert "005930.KS" in rows
    assert rows["005930.KS"]["close"] == 105.0

def test_store_prices_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("MDB_DATA_DIR", str(tmp_path))
    import store; importlib.reload(store)
    store.write_prices("us", "2026-07-19", {"NVDA": {"name": "엔비디아", "daily_return": 2.5}})
    _, rows = store.read_latest_prices("us", "2026-07-19")
    assert rows["NVDA"]["daily_return"] == 2.5
