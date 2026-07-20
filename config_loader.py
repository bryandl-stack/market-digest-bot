"""로컬 config/*.json 로드 — Firestore 설정 컬렉션 읽기 대체.
sectors_* → universe.json, settings/keywords → keywords.json,
settings/telegram_channels → channels.json. user_settings 합산은 미지원."""
import json
import os
import re

CONFIG_DIR = os.environ.get("MDB_CONFIG_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config")


def _load(name):
    path = os.path.join(CONFIG_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_universe(countries=None):
    uni = _load("universe.json") or {}
    countries = countries or list(uni.keys())
    name_to_info, ticker_to_name, ticker_country = {}, {}, {}
    for c in countries:
        for sec in uni.get(c, []):
            for st in sec.get("stocks", []):
                ticker = (st.get("ticker") or "").strip()
                if not ticker:
                    continue
                name_kr = (st.get("nameKr") or st.get("name") or "").strip()
                name_en = (st.get("nameEn") or "").strip()
                base = {"ticker": ticker, "sector_id": sec.get("id", ""),
                        "sector_name": sec.get("name", "")}
                if name_kr:
                    name_to_info[name_kr] = {**base, "name_type": "kr"}
                if name_en:
                    name_to_info[name_en] = {**base, "name_type": "en"}
                ticker_to_name[ticker] = name_kr or name_en or ticker
                ticker_country[ticker] = c
    return name_to_info, ticker_to_name, ticker_country


def load_keywords(name_to_info):
    kw = _load("keywords.json") or {}
    for ticker, kw_str in kw.items():
        base = next((i for i in name_to_info.values() if i["ticker"] == ticker), None)
        if base is None:
            continue
        binfo = {k: v for k, v in base.items() if k != "name_type"}
        for k in (kw_str or "").split(","):
            k = k.strip()
            if not k or k in name_to_info:
                continue
            name_to_info[k] = {**binfo,
                               "name_type": "kr" if re.search(r"[가-힣]", k) else "en"}
    return name_to_info


def load_channels():
    return _load("channels.json") or []
