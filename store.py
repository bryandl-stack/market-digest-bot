"""로컬 파일 기반 저장소 — Firestore(firestore.client()) 대체.
comments(뉴스)·prices·macro·calendar 를 data/ 아래 JSON/JSONL 로 읽고 쓴다."""
import json
import os
from collections import defaultdict

DATA_DIR = os.environ.get("MDB_DATA_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data")


def _p(*parts):
    path = os.path.join(DATA_DIR, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


# ── comments (뉴스 원천) ─────────────────────────────────────────
def _comments_path(date_str):
    return _p("comments", f"{date_str}.jsonl")


def _serialize(item):
    o = dict(item)
    o.pop("_terms", None)                       # set — 점수 계산 후 저장 안 함
    ts = o.get("timestamp")
    if hasattr(ts, "isoformat"):
        o["timestamp"] = ts.isoformat()
    return o


def read_comments(dates):
    out = []
    for ds in dates:
        path = os.path.join(DATA_DIR, "comments", f"{ds}.jsonl")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    return out


def existing_links(date_str):
    return {c.get("tg_link", "") for c in read_comments([date_str])}


def existing_headlines(date_str):
    return [c.get("headline", "") for c in read_comments([date_str]) if c.get("headline")]


def append_comments(items):
    by_date = defaultdict(list)
    for it in items:
        by_date[it["date"]].append(_serialize(it))
    total = 0
    for ds, lst in by_date.items():
        with open(_comments_path(ds), "a", encoding="utf-8") as f:
            for o in lst:
                f.write(json.dumps(o, ensure_ascii=False) + "\n")
        total += len(lst)
    return total


# ── prices (주가) ────────────────────────────────────────────────
def write_prices(market, date_str, rows):
    with open(_p("prices", market, f"{date_str}.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)


def read_latest_prices(market, on_or_before):
    d = os.path.join(DATA_DIR, "prices", market)
    if not os.path.isdir(d):
        return None, {}
    dates = sorted(fn[:-5] for fn in os.listdir(d)
                   if fn.endswith(".json") and fn[:-5] <= on_or_before)
    if not dates:
        return None, {}
    with open(os.path.join(d, f"{dates[-1]}.json"), encoding="utf-8") as f:
        return dates[-1], json.load(f)


# ── macro / calendar ────────────────────────────────────────────
def write_macro(series):
    with open(_p("macro_1d.json"), "w", encoding="utf-8") as f:
        json.dump({"series": series}, f, ensure_ascii=False)


def read_macro():
    path = os.path.join(DATA_DIR, "macro_1d.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("series", {})


def write_calendar(economic, earnings):
    with open(_p("calendar.json"), "w", encoding="utf-8") as f:
        json.dump({"economic": economic, "earnings": earnings}, f, ensure_ascii=False)


def read_calendar():
    path = os.path.join(DATA_DIR, "calendar.json")
    if not os.path.exists(path):
        return {"economic": [], "earnings": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)
