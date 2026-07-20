import json, os, importlib

def _loader(tmp_path, universe=None, keywords=None, channels=None):
    cfg = tmp_path / "config"
    cfg.mkdir(exist_ok=True)
    if universe is not None:
        (cfg / "universe.json").write_text(json.dumps(universe), encoding="utf-8")
    if keywords is not None:
        (cfg / "keywords.json").write_text(json.dumps(keywords), encoding="utf-8")
    if channels is not None:
        (cfg / "channels.json").write_text(json.dumps(channels), encoding="utf-8")
    os.environ["MDB_CONFIG_DIR"] = str(cfg)
    import config_loader
    importlib.reload(config_loader)
    return config_loader

UNI = {"us": [{"id": "s1", "name": "반도체",
               "stocks": [{"ticker": "NVDA", "nameKr": "엔비디아", "nameEn": "NVIDIA"}]}],
       "kr": [{"id": "s2", "name": "반도체",
               "stocks": [{"ticker": "005930.KS", "nameKr": "삼성전자", "nameEn": "Samsung"}]}]}

def test_load_universe_maps_kr_and_en_names(tmp_path):
    cl = _loader(tmp_path, universe=UNI)
    n2i, t2n, tc = cl.load_universe(["us"])
    assert n2i["엔비디아"]["ticker"] == "NVDA" and n2i["엔비디아"]["name_type"] == "kr"
    assert n2i["NVIDIA"]["name_type"] == "en"
    assert t2n["NVDA"] == "엔비디아" and tc["NVDA"] == "us"
    assert "삼성전자" not in n2i  # kr 국가 미포함

def test_load_universe_all_countries_when_none(tmp_path):
    cl = _loader(tmp_path, universe=UNI)
    n2i, _, tc = cl.load_universe(None)
    assert "삼성전자" in n2i and tc["005930.KS"] == "kr"

def test_load_keywords_adds_aliases(tmp_path):
    cl = _loader(tmp_path, universe=UNI, keywords={"NVDA": "엔디비아,젠슨황"})
    n2i, _, _ = cl.load_universe(["us"])
    n2i = cl.load_keywords(n2i)
    assert n2i["엔디비아"]["ticker"] == "NVDA" and n2i["엔디비아"]["name_type"] == "kr"
    assert n2i["젠슨황"]["ticker"] == "NVDA"

def test_load_channels_and_missing_files(tmp_path):
    cl = _loader(tmp_path, universe=UNI, channels=["chan_a", "chan_b"])
    assert cl.load_channels() == ["chan_a", "chan_b"]
    # 파일 없으면 빈 값
    (tmp_path / "config" / "channels.json").unlink()
    importlib_reload = __import__("importlib").reload
    importlib_reload(cl)
    assert cl.load_channels() == []
