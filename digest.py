#!/usr/bin/env python3
"""market-digest-bot → 텔레그램 봇 다이제스트 (파일 기반 store).

서브커맨드:
  dump            데이터(뉴스=당일+전일, 주가/매크로/캘린더)를 stdout으로 출력(요약 없음).
  send <textfile> 텍스트 파일 내용을 텔레그램 봇으로 전송(Bot API, 1:1 DM/그룹/채널).
  chatid          봇의 getUpdates에서 최근 chat_id 목록 출력(설정용 헬퍼).
전송에는 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수가 필요하다(.env).
요약은 이 스크립트가 하지 않는다 — run_digest.sh 가 claude -p 로 수행.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _env import load_env
load_env()
import store

KST = "Asia/Seoul"
MARKETS = {"us": "us", "eu": "eu", "jp": "jp", "kr": "kr"}
TIER_RANK = {"very_high": 0, "high": 1, "medium": 2, "low": 3, "very_low": 4}
NEWS_LIMIT = 30      # 덤프에 담을 뉴스 최대 건수(요약은 claude가 취사선택)
MOVERS_N = 3         # 시장별 상·하위 종목 수
# macro_data/1d series_json의 실제 키(친근한 이름). 디지스트에 노출할 주요 지표만 선별.
MACRO_KEYS = ["sp500", "nasdaq", "dow", "kospi", "nikkei", "us10y", "us2y", "dxy", "usdkrw", "usdjpy", "wti", "gold"]
MACRO_LABELS = {
    "sp500": "S&P500", "nasdaq": "나스닥", "dow": "다우", "kospi": "코스피",
    "nikkei": "닛케이", "us10y": "미 10년물", "us2y": "미 2년물", "dxy": "달러인덱스",
    "usdkrw": "USD/KRW", "usdjpy": "USD/JPY", "wti": "WTI", "gold": "금",
}


def _today_kst():
    import pytz
    from datetime import datetime
    return datetime.now(pytz.timezone(KST)).strftime("%Y-%m-%d")


def _yesterday_kst(date_str):
    from datetime import date, timedelta
    return (date.fromisoformat(date_str) - timedelta(days=1)).isoformat()


def fetch_digest_data(date_str):
    # 1) 뉴스: 당일+전일 윈도우(이른 시각·주말 공백 방지) → 메모리에서 uid 필터
    #    claude가 당일 우선 + 중요도 기준으로 최종 선별/요약한다.
    yday = _yesterday_kst(date_str)
    news = []
    for d in store.read_comments([yday, date_str]):
        if d.get("uid") != "telegram_crawler":
            continue
        tickers = sorted({t for lst in (d.get("tickers") or {}).values() for t in lst})
        news.append({
            "date": d.get("date", ""),
            "tier": d.get("importanceTier", "very_low"),
            "score": float(d.get("importanceScore", 0) or 0),
            "headline": d.get("headline") or (d.get("text") or "")[:80],
            "tickers": tickers,
            "author": d.get("author", "?"),
            "link": d.get("tg_link") or d.get("link") or "",
            # 증권사 레포트(목표주가·투자의견) 추출용 본문 일부
            "body": (d.get("text") or "").strip().replace("\n", " ")[:300],
        })
    # 당일(date_str) 우선, 그다음 중요도
    news.sort(key=lambda n: (n["date"] != date_str, -n["score"], TIER_RANK.get(n["tier"], 9)))
    news = news[:NEWS_LIMIT]

    # 2) 주가: 시장별 on_or_before 최신 날짜의 종목
    markets = {}
    for mkt, key in MARKETS.items():
        mdate, rows = store.read_latest_prices(key, date_str)
        if not mdate:
            continue
        rows_l = [{"name": v.get("name", tk), "ret": float(v["daily_return"])}
                  for tk, v in rows.items() if v.get("daily_return") is not None]
        if not rows_l:
            continue
        rows_l.sort(key=lambda x: x["ret"], reverse=True)
        markets[mkt] = {"date": mdate, "gainers": rows_l[:MOVERS_N],
                        "losers": rows_l[-MOVERS_N:][::-1]}

    # 3) 매크로: macro 시리즈
    macro = []
    series = store.read_macro()
    for key in MACRO_KEYS:
        s = series.get(key)
        if not s or not s.get("c"):
            continue
        close = s["c"][-1]
        if close is None:
            continue
        prev = s.get("prev_close")
        if prev is None and len(s["c"]) >= 2:
            prev = s["c"][-2]
        chg = round((close / prev - 1) * 100, 2) if prev else None
        macro.append({"name": MACRO_LABELS.get(key, key), "close": close, "change_pct": chg})

    # 4) 캘린더: 오늘 이후만
    economic, earnings = [], []
    cal = store.read_calendar()
    for e in cal.get("economic", []):
        if e.get("date", "") >= date_str:
            economic.append({"date": e["date"], "time": e.get("time", ""),
                             "event": e.get("event", ""), "forecast": e.get("forecast"),
                             "previous": e.get("previous")})
    for e in cal.get("earnings", []):
        if e.get("date", "") >= date_str:
            earnings.append({"date": e["date"], "symbol": e.get("symbol", "?")})
    economic = economic[:15]
    earnings = earnings[:20]
    return {"date": date_str, "news": news, "markets": markets, "macro": macro,
            "calendar": {"economic": economic, "earnings": earnings}}


def split_message(text, limit=4096):
    """줄 경계 기준으로 limit 이하 청크 리스트 반환. 긴 줄은 강제 분할."""
    if not text:
        return []
    chunks, cur = [], ""
    for line in text.split("\n"):
        # 한 줄이 통째로 limit 초과 → 강제로 잘라 넣기
        while len(line) > limit:
            if cur:
                chunks.append(cur); cur = ""
            chunks.append(line[:limit]); line = line[limit:]
        add = line if not cur else "\n" + line
        if len(cur) + len(add) > limit:
            chunks.append(cur); cur = line
        else:
            cur += add
    if cur:
        chunks.append(cur)
    return chunks


def to_html(text):
    """HTML parse_mode용 변환: & < > 이스케이프 후 **bold** → <b>bold</b>.
    URL은 그대로 둬도 텔레그램이 자동 링크. 본문의 &·<·>는 자동 처리되어 전송 실패 위험 없음."""
    import re, html
    esc = html.escape(text, quote=False)  # & < > 만 변환(따옴표 유지)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)


def _fmt_pct(v):
    return "n/a" if v is None else f"{v:+.2f}%"


def format_dump(data):
    """fetch_digest_data 결과 dict → 사람이 읽는 텍스트(요약 입력용)."""
    L = [f"=== 시장 다이제스트 데이터 덤프 ({data['date']} KST) ==="]

    L.append("\n[📈 주가 등락] (시장별 일간수익률 상·하위)")
    if data["markets"]:
        for mkt, m in data["markets"].items():
            L.append(f"  {mkt} ({m['date']}):")
            L.append("    상위: " + (", ".join(f"{g['name']} {g['ret']:+.2f}%" for g in m["gainers"]) or "-"))
            L.append("    하위: " + (", ".join(f"{x['name']} {x['ret']:+.2f}%" for x in m["losers"]) or "-"))
    else:
        L.append("  데이터 없음")

    # 뉴스 원천: claude가 여기서 '핵심 뉴스'(티커 제외)와 '증권사 레포트'(목표주가·투자의견)를 분리해 작성.
    L.append(f"\n[📰 뉴스·레포트 원천] (당일={data['date']}+전일, 당일 우선·중요도 내림차순, uid=telegram_crawler)")
    if data["news"]:
        for n in data["news"]:
            tk = ",".join(n.get("tickers") or []) or "-"
            day = n.get("date", "")
            L.append(f"- [{day}] ({n['tier']}/{n['score']:.0f}) {n['headline']}")
            L.append(f"    종목:{tk} | 출처:{n.get('author', '?')} | 링크:{n.get('link', '')}")
            if n.get("body"):
                L.append(f"    본문:{n['body']}")
    else:
        L.append("- 데이터 없음")

    L.append("\n[🌐 매크로] (1d, 전일 대비)")
    if data["macro"]:
        for s in data["macro"]:
            L.append(f"- {s['name']}: {s['close']} ({_fmt_pct(s['change_pct'])})")
    else:
        L.append("- 데이터 없음")

    L.append("\n[🗓 캘린더] (예정 경제지표/실적)")
    cal = data["calendar"]
    if cal["economic"]:
        for e in cal["economic"]:
            extra = f" 예상:{e['forecast']} 이전:{e['previous']}" if e.get("forecast") or e.get("previous") else ""
            L.append(f"- 경제 {e['date']} {e['time']} {e['event']}{extra}")
    if cal["earnings"]:
        for e in cal["earnings"]:
            L.append(f"- 실적 {e['date']} {e['symbol']}")
    if not cal["economic"] and not cal["earnings"]:
        L.append("- 데이터 없음")

    return "\n".join(L)


def main(argv):
    if len(argv) < 2 or argv[1] not in ("dump", "send", "chatid"):
        print("사용법: digest.py [dump | send <textfile> | chatid]", file=sys.stderr)
        return 1
    if argv[1] == "dump":
        return _cmd_dump()
    if argv[1] == "chatid":
        return _cmd_chatid()
    return _cmd_send(argv[2] if len(argv) > 2 else None)


def _cmd_dump():
    print(format_dump(fetch_digest_data(_today_kst())))
    return 0


def _bot_api(method, params):
    """텔레그램 Bot API 호출. (ok, result_or_error) 반환."""
    import urllib.request, urllib.parse, json as _json
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN 환경변수가 필요합니다(.env).")
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode() if params else None
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=30) as r:
        resp = _json.loads(r.read())
    return resp.get("ok", False), resp


def _cmd_send(path):
    if not path or not os.path.isfile(path):
        print(f"전송할 텍스트 파일이 필요합니다: {path}", file=sys.stderr)
        return 1
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        print("빈 메시지 — 전송 생략", file=sys.stderr)
        return 1
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not chat_id:
        print("TELEGRAM_CHAT_ID 환경변수가 필요합니다(.env). `chatid`로 확인하세요.", file=sys.stderr)
        return 1
    sent = 0
    for chunk in split_message(to_html(text)):
        ok, resp = _bot_api("sendMessage", {"chat_id": chat_id, "text": chunk,
                                            "parse_mode": "HTML",
                                            "disable_web_page_preview": "true"})
        if not ok:
            print(f"전송 실패: {resp}", file=sys.stderr)
            return 1
        sent += len(chunk)
    print(f"전송 완료: {sent}자")
    return 0


def _cmd_chatid():
    """봇에게 메시지를 보낸 적 있는 chat들의 id를 출력(설정용)."""
    ok, resp = _bot_api("getUpdates", {})
    if not ok:
        print(f"getUpdates 실패: {resp}", file=sys.stderr)
        return 1
    seen = {}
    for u in resp.get("result", []):
        msg = u.get("message") or u.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if chat.get("id") is not None:
            seen[chat["id"]] = f"{chat.get('type')} {chat.get('title') or chat.get('username') or chat.get('first_name', '')}".strip()
    if not seen:
        print("업데이트 없음 — 봇에게 먼저 메시지(/start)를 보낸 뒤 다시 실행하세요.", file=sys.stderr)
        return 1
    for cid, desc in seen.items():
        print(f"{cid}\t{desc}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
