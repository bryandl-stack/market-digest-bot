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

def test_store_prices_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("MDB_DATA_DIR", str(tmp_path))
    import store; importlib.reload(store)
    store.write_prices("us", "2026-07-19", {"NVDA": {"name": "엔비디아", "daily_return": 2.5}})
    _, rows = store.read_latest_prices("us", "2026-07-19")
    assert rows["NVDA"]["daily_return"] == 2.5
