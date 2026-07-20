import os, sys, json, shutil, importlib

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
CONFIG = os.path.join(ROOT, "config")


def _load_default(name):
    with open(os.path.join(CONFIG, name), encoding="utf-8") as f:
        return json.load(f)


def test_default_files_are_valid_json():
    uni = _load_default("universe.default.json")
    kw = _load_default("keywords.default.json")
    ch = _load_default("channels.default.json")
    assert isinstance(uni, dict) and isinstance(kw, dict) and isinstance(ch, list)


def test_default_universe_covers_four_markets_and_is_large():
    uni = _load_default("universe.default.json")
    assert set(uni.keys()) >= {"us", "eu", "jp", "kr"}
    total = sum(len(sec["stocks"]) for c in uni.values() for sec in c)
    assert total >= 80, f"기본 유니버스가 너무 작음: {total}종목"
    for c in ("us", "eu", "jp", "kr"):
        assert any(sec["stocks"] for sec in uni[c]), f"{c} 시장에 종목 없음"


def test_default_channels_present():
    ch = _load_default("channels.default.json")
    assert len(ch) >= 5
    assert all(isinstance(x, str) and x for x in ch)


def test_config_loader_parses_defaults(tmp_path, monkeypatch):
    """default 파일들을 실제 config/*.json 위치로 복사하면 config_loader가 파싱한다."""
    cfg = tmp_path / "config"; cfg.mkdir()
    for base in ("universe", "keywords", "channels"):
        shutil.copy(os.path.join(CONFIG, f"{base}.default.json"), cfg / f"{base}.json")
    monkeypatch.setenv("MDB_CONFIG_DIR", str(cfg))
    import config_loader; importlib.reload(config_loader)

    name_to_info, ticker_to_name, ticker_country = config_loader.load_universe(None)
    assert len(ticker_to_name) >= 80
    assert {"us", "eu", "jp", "kr"} <= set(ticker_country.values())

    # 키워드 별칭이 유니버스 티커에 매핑되어 name_to_info를 넓힌다
    before = len(name_to_info)
    name_to_info = config_loader.load_keywords(name_to_info)
    assert len(name_to_info) >= before

    assert len(config_loader.load_channels()) >= 5
