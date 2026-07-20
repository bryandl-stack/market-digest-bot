#!/usr/bin/env python3
"""매크로(1d) + 캘린더(경제지표·실적)를 로컬 파일로 수집.
api_server.py 의 fetch_macro/fetch_calendar 를 자립화(Firestore 제거).

사용법:
  python3 crawlers/fetch_macro_calendar.py   # data/macro_1d.json + data/calendar.json

FRED_API_KEY 가 없으면 forward 경제지표 보강만 스킵(ForexFactory·실적은 정상)."""
import os
import sys
import logging
import concurrent.futures
from datetime import datetime, timedelta

import requests
import pytz
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _env import load_env
load_env()
import store
import config_loader

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("macro_calendar")

# ── 매크로 종목 (원본 api_server.MACRO_INSTRUMENTS 그대로) ──
# (key, label, yahoo ticker, category)
MACRO_INSTRUMENTS = [
    # 지수: 거의 24시간 거래되는 선물로 표시(유로/홍콩/상해/코스피는 yf 선물 없어 현물 유지)
    ("sp500",     "S&P 500",      "ES=F",      "index"),
    ("nasdaq",    "나스닥 종합",   "NQ=F",      "index"),
    ("dow",       "다우존스",      "YM=F",      "index"),
    ("kospi",     "코스피",        "^KS11",     "index"),
    ("nikkei",    "닛케이 225",    "NKD=F",     "index"),
    ("eurostoxx", "유로스톡스 50", "^STOXX50E", "index"),
    ("dax",       "DAX",          "^GDAXI",    "index"),
    ("ftse",      "FTSE 100",     "^FTSE",     "index"),
    ("hsi",       "항셍",          "^HSI",      "index"),
    ("shanghai",  "상해종합",      "000001.SS", "index"),
    # 국채: 24시간 거래되는 선물(가격) — 값은 수익률%가 아니라 선물가격
    ("us2y",      "미국 2년",      "ZT=F",      "rate"),
    ("us5y",      "미국 5년",      "ZF=F",      "rate"),
    ("us10y",     "미국 10년",     "ZN=F",      "rate"),
    ("us30y",     "미국 30년",     "ZB=F",      "rate"),
    ("dxy",       "달러인덱스",    "DX-Y.NYB",  "fx"),
    ("eurusd",    "EUR/USD",      "EURUSD=X",  "fx"),
    ("usdjpy",    "USD/JPY",      "USDJPY=X",  "fx"),
    ("usdkrw",    "USD/KRW",      "USDKRW=X",  "fx"),
    ("gbpusd",    "GBP/USD",      "GBPUSD=X",  "fx"),
    ("usdcny",    "USD/CNY",      "USDCNY=X",  "fx"),
    ("wti",       "WTI 유가",      "CL=F",      "commodity"),
    ("brent",     "브렌트유",      "BZ=F",      "commodity"),
    ("gold",      "금",            "GC=F",      "commodity"),
    ("silver",    "은",            "SI=F",      "commodity"),
]

# 캘린더: 경제지표(ForexFactory 무키 이번주 + FRED forward 선택) + 추적종목 실적(yfinance)
FRED_API_KEY         = os.environ.get("FRED_API_KEY")  # 다음주 이후 발표 일정 보강(선택)
FF_CALENDAR_URL      = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FRED_RELEASES_URL    = "https://api.stlouisfed.org/fred/releases/dates"
CALENDAR_PAST_DAYS   = 7      # -1주
CALENDAR_FUTURE_DAYS = 14     # +2주

# FRED 주요 릴리스명 → 한글 라벨 (forward 일정 표기용)
FRED_MAJOR = [
    ("consumer price index", "CPI"),
    ("producer price index", "PPI"),
    ("employment situation", "고용보고서(NFP)"),
    ("gross domestic product", "GDP"),
    ("personal income and outlays", "PCE 물가"),
    ("advance monthly sales for retail", "소매판매"),
    ("import and export price", "수출입물가"),
]


def fetch_macro():
    """매크로 전 종목의 종가 시계열을 yfinance로 받아 data/macro_1d.json 에 저장.
    라인 차트용이라 종가만 저장. 시간은 절대 epoch(초)로 통일(프론트가 KST로 표시).
    반환: series dict."""
    timeframe = "1d"
    cfg = {"interval": "1d", "period": "2y"}

    tickers = [tk for (_, _, tk, _) in MACRO_INSTRUMENTS]
    logger.info("=== 매크로 수집 시작 [%s]: %d종목 ===", timeframe, len(tickers))
    raw = yf.download(tickers, interval=cfg["interval"], period=cfg["period"],
                      auto_adjust=True, progress=False)
    o_df, h_df, l_df, c_df = raw["Open"], raw["High"], raw["Low"], raw["Close"]  # 컬럼=티커

    def _r(v):
        try:
            f = float(v)
            return None if f != f else round(f, 4)   # NaN → None
        except Exception:
            return None

    series = {}
    for key, label, tk, cat in MACRO_INSTRUMENTS:
        try:
            if tk not in c_df.columns:
                continue
            c = c_df[tk].dropna()
            if c.empty:
                continue
            idx = c.index
            o = o_df[tk].reindex(idx) if tk in o_df.columns else None
            h = h_df[tk].reindex(idx) if tk in h_df.columns else None
            l = l_df[tk].reindex(idx) if tk in l_df.columns else None
            tsidx = idx.tz_localize("UTC") if idx.tz is None else idx  # 일봉(naive)→UTC
            n = len(c)
            series[key] = {
                "t": [int(x.timestamp()) for x in tsidx],
                "o": [_r(v) for v in (o.values if o is not None else [None] * n)],
                "h": [_r(v) for v in (h.values if h is not None else [None] * n)],
                "l": [_r(v) for v in (l.values if l is not None else [None] * n)],
                "c": [_r(v) for v in c.values],
            }
        except Exception as e:
            logger.warning("매크로 종목 실패 %s(%s): %s", key, tk, e)

    # ── 일간 등락률 기준값(prev_close) ──
    # 일봉을 받아 직전 종가를 prev_close로 저장한다.
    try:
        d_close = yf.download(tickers, interval="1d", period="10d",
                              auto_adjust=True, progress=False)["Close"]
        for key, _label, tk, _cat in MACRO_INSTRUMENTS:
            if key not in series or tk not in d_close.columns:
                continue
            col = d_close[tk].dropna()
            if len(col) >= 2:
                series[key]["prev_close"] = _r(col.iloc[-2])
    except Exception as e:
        logger.warning("매크로 prev_close 계산 실패: %s", e)

    store.write_macro(series)
    logger.info("=== 매크로 수집 완료 [%s]: %d종목 ===", timeframe, len(series))
    return series


def _norm_label(s):
    return "".join((s or "").lower().split())


def _fred_major_label(name):
    n = (name or "").lower()
    for kw, lab in FRED_MAJOR:
        if kw in n:
            return lab
    return None


def _earnings_for_ticker(tk, country, frm_s, to_s):
    """yfinance에서 한 티커의 윈도우 내 실적일 목록(국가·예상매출 포함)."""
    def num(v):
        try:
            f = float(v)
            return None if f != f else round(f, 4)   # NaN 제외
        except Exception:
            return None
    try:
        t = yf.Ticker(tk)
        df = t.get_earnings_dates(limit=8)
        if df is None or not len(df):
            return []
        out = []
        for idx, row in df.iterrows():
            d = idx.date().strftime("%Y-%m-%d")
            if not (frm_s <= d <= to_s):
                continue
            out.append({"date": d, "symbol": tk, "country": country,
                        "epsEstimated": num(row.get("EPS Estimate")),
                        "eps": num(row.get("Reported EPS"))})
        # 예상 매출: 아직 미발표(eps None)인 실적에만 당분기(0q) 애널리스트 평균 추정 부착
        if any(e["eps"] is None for e in out):
            try:
                rev = t.revenue_estimate
                if rev is not None and "0q" in rev.index:
                    avg = num(rev.loc["0q", "avg"])
                    ccy = rev.loc["0q", "currency"] if "currency" in rev.columns else None
                    if avg is not None:
                        for e in out:
                            if e["eps"] is None:
                                e["revenueEstimated"] = avg
                                if ccy:
                                    e["revenueCcy"] = str(ccy)
            except Exception:
                pass
        return out
    except Exception:
        return []


def fetch_calendar():
    """경제지표(ForexFactory 이번주 + FRED forward) + 추적종목 실적(yfinance)을
    data/calendar.json 에 저장. 날짜·시각은 KST 표시 문자열로 미리 계산.
    반환: (economic, earnings)."""
    kst = pytz.timezone("Asia/Seoul")
    today = datetime.now(kst).date()
    frm = today - timedelta(days=CALENDAR_PAST_DAYS)
    to  = today + timedelta(days=CALENDAR_FUTURE_DAYS)
    frm_s, to_s = frm.strftime("%Y-%m-%d"), to.strftime("%Y-%m-%d")

    economic = []
    # 1) ForexFactory 이번주 (미국 고영향, forecast/previous/actual 포함)
    try:
        r = requests.get(FF_CALENDAR_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        r.raise_for_status()
        for e in (r.json() or []):
            if e.get("country") != "USD" or (e.get("impact") or "") != "High":
                continue
            try:
                dt = datetime.fromisoformat(e["date"]).astimezone(kst)
            except Exception:
                continue
            ds = dt.strftime("%Y-%m-%d")
            if not (frm_s <= ds <= to_s):
                continue
            economic.append({
                "date": ds, "time": dt.strftime("%H:%M"), "event": e.get("title"),
                "forecast": e.get("forecast"), "previous": e.get("previous"),
                "actual": e.get("actual"), "scheduled": False,
            })
    except Exception as ex:
        logger.warning("ForexFactory 수집 실패: %s", ex)

    # 2) FRED forward 일정 (키 있을 때만). FF가 이미 다룬 날짜/지표는 제외.
    if FRED_API_KEY:
        try:
            r = requests.get(FRED_RELEASES_URL, params={
                "api_key": FRED_API_KEY, "file_type": "json",
                "include_release_dates_with_no_data": "true",
                "realtime_start": frm_s, "realtime_end": to_s,
                "sort_order": "asc", "limit": 1000,
            }, timeout=20)
            r.raise_for_status()
            seen = {(x["date"], _norm_label(x["event"])) for x in economic}
            for rd in (r.json().get("release_dates") or []):
                lab = _fred_major_label(rd.get("release_name"))
                d = rd.get("date")
                if not lab or not d or not (frm_s <= d <= to_s):
                    continue
                if (d, _norm_label(lab)) in seen:
                    continue
                if any(x["date"] == d and _norm_label(lab) in _norm_label(x["event"]) for x in economic):
                    continue
                seen.add((d, _norm_label(lab)))
                economic.append({"date": d, "time": "", "event": f"{lab} 발표", "scheduled": True})
        except Exception as ex:
            logger.warning("FRED 수집 실패: %s", ex)

    economic.sort(key=lambda x: (x["date"], x.get("time") or ""))

    # 3) 실적 (yfinance, 추적종목 병렬)
    earnings = []
    _n, _t2n, tracked = config_loader.load_universe(None)   # {ticker: country}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(_earnings_for_ticker, tk, ctry, frm_s, to_s) for tk, ctry in tracked.items()]
        for f in concurrent.futures.as_completed(futs):
            earnings.extend(f.result())
    earnings.sort(key=lambda x: (x["date"], x["symbol"]))

    store.write_calendar(economic, earnings)
    logger.info("캘린더 수집 완료: 경제 %d, 실적 %d (%s~%s)", len(economic), len(earnings), frm_s, to_s)
    return economic, earnings


def main():
    try:
        fetch_macro()
    except Exception as e:
        logger.error("매크로 실패: %s", e)
    try:
        fetch_calendar()
    except Exception as e:
        logger.error("캘린더 실패: %s", e)


if __name__ == "__main__":
    main()
