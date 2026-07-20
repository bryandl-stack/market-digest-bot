import os, sys, importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "crawlers"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_fred_label_matching():
    import fetch_macro_calendar as m; importlib.reload(m)
    assert m._fred_major_label("Consumer Price Index") == "CPI"
    assert m._fred_major_label("Some Minor Release") is None


def test_macro_instruments_cover_digest_keys():
    import fetch_macro_calendar as m; importlib.reload(m)
    keys = {k for (k, _l, _t, _c) in m.MACRO_INSTRUMENTS}
    for need in ["sp500", "nasdaq", "dow", "kospi", "nikkei", "us10y", "us2y",
                 "dxy", "usdkrw", "usdjpy", "wti", "gold"]:
        assert need in keys, need


def test_fetch_calendar_skips_fred_without_key(monkeypatch, tmp_path):
    monkeypatch.setenv("MDB_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    import store; importlib.reload(store)
    import fetch_macro_calendar as m; importlib.reload(m)
    m.store = store
    m.FRED_API_KEY = None
    monkeypatch.setattr(m.requests, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no net")))
    monkeypatch.setattr(m, "config_loader", type("C", (), {"load_universe": staticmethod(lambda c: ({}, {}, {}))}))
    eco, earn = m.fetch_calendar()   # 예외 삼키고 빈 결과
    assert eco == [] and earn == []
