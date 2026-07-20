#!/usr/bin/env python3
"""
독립 실행형 시장 데이터 수집 스크립트.
config/universe.json 에서 티커를 읽어 data/prices/<market>/<date>.json 에 저장합니다.

사용법:
  python3 fetch_prices.py            # 미국, 오늘(ET) 거래일
  python3 fetch_prices.py eu         # 유럽, 오늘(CET) 거래일
  python3 fetch_prices.py jp 2026-05-28
  python3 fetch_prices.py 2026-05-28 # 미국 + 날짜 지정 (구버전 호환)

cron 등록 예시 (각 시장 마감 30분 후, UTC 고정):
  0 23 * * * python3 .../fetch_prices.py us >> .../fetch_prices.log 2>&1
  0 17 * * * python3 .../fetch_prices.py eu >> .../fetch_prices.log 2>&1
  0 7  * * * python3 .../fetch_prices.py jp >> .../fetch_prices.log 2>&1
  5 7  * * * python3 .../fetch_prices.py kr >> .../fetch_prices.log 2>&1
"""
import concurrent.futures
import logging
import os
import re
import sys
from datetime import datetime, timedelta

import pytz
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import store
import config_loader


# ── 국가별 타임존 ──────────────────────────────────────────────
COUNTRY_TZ = {
    "us": "America/New_York",
    "eu": "Europe/Berlin",
    "jp": "Asia/Tokyo",
    "kr": "Asia/Seoul",
}


def fetch_market_caps(tickers):
    """시가총액 + 상장 통화 + 당일 시가/현재가를 병렬 조회.
    반환: ({ticker: cap}, {ticker: currency}, {ticker: open}, {ticker: last}).
    open/last는 일봉 다운로드가 NaN을 줄 때(아시아 장 마감 직후 등) intraday 계산 폴백용."""
    caps = {}
    currencies = {}
    opens = {}
    lasts = {}
    def get_one(ticker):
        try:
            fi = yf.Ticker(ticker).fast_info
            cap = fi.market_cap
            cur = getattr(fi, "currency", None)
            op  = getattr(fi, "open", None)
            lp  = getattr(fi, "last_price", None)
            return (ticker, (int(cap) if cap else None), (cur.upper() if cur else None),
                    (float(op) if op else None), (float(lp) if lp else None))
        except Exception:
            return ticker, None, None, None, None
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for ticker, cap, cur, op, lp in ex.map(get_one, tickers):
            if cap:
                caps[ticker] = cap
            if cur:
                currencies[ticker] = cur
            if op:
                opens[ticker] = op
            if lp:
                lasts[ticker] = lp
    return caps, currencies, opens, lasts


def get_fx_to_usd(currencies):
    """통화 코드 집합 → {통화: USD 환산 배율}. USD=1.0. 실패 통화는 누락(정규화 생략)."""
    rates = {"USD": 1.0}
    targets = {c for c in currencies if c and c != "USD"}
    def get_one(cur):
        # yfinance: '<CUR>USD=X' = 해당 통화 1단위의 USD 가치
        try:
            px = yf.Ticker(f"{cur}USD=X").fast_info.last_price
            return cur, (float(px) if px else None)
        except Exception:
            return cur, None
    if targets:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for cur, px in ex.map(get_one, targets):
                if px:
                    rates[cur] = px
    return rates

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ── 데이터 수집 및 저장 ───────────────────────────────────────

def fetch_and_store(date_str: str, market: str, is_today: bool = True) -> None:
    """yfinance로 데이터 수집 후 data/prices/{market}/{date}.json 에 저장."""
    # 추적 티커·표시명 (로컬 config)
    _n2i, ticker_to_name, ticker_country = config_loader.load_universe([market])
    tickers = [tk for tk, c in ticker_country.items() if c == market]
    if not tickers:
        logger.warning("universe.json 에 %s 시장 종목이 없습니다.", market)
        return

    logger.info("다운로드 시작 — 티커 %d개: %s", len(tickers), tickers)

    import pandas as pd
    target_date = pd.Timestamp(date_str)
    end_dt      = target_date + timedelta(days=1)
    start_dt    = target_date - timedelta(days=400)

    # yfinance 다운로드
    if len(tickers) == 1:
        raw   = yf.download(tickers[0], start=start_dt.strftime("%Y-%m-%d"),
                            end=end_dt.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
        close = raw["Close"].to_frame(name=tickers[0])
        open_ = raw["Open"].to_frame(name=tickers[0])
    else:
        raw   = yf.download(tickers, start=start_dt.strftime("%Y-%m-%d"),
                            end=end_dt.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
        close = raw["Close"]
        open_ = raw["Open"]

    logger.info("다운로드 완료: %d rows × %d cols", *close.shape)

    # 시가총액 + 통화 + 당일 시가/현재가 병렬 조회, USD 환율 조회
    logger.info("시가총액 조회 중...")
    market_caps, currencies, fi_opens, fi_lasts = fetch_market_caps(tickers)
    fx = get_fx_to_usd(set(currencies.values()))
    logger.info("시가총액 조회 완료: %d개 / 환율: %s", len(market_caps),
                {k: round(v, 4) for k, v in fx.items()})

    rows = {}   # ticker -> 필드 dict

    for ticker in tickers:
        if ticker not in close.columns:
            logger.warning("컬럼 없음 (상장폐지/잘못된 티커?): %s", ticker)
            continue

        # 요청 날짜 이하 데이터만 사용
        series = close[ticker].dropna()
        series = series[series.index.normalize() <= target_date]

        if len(series) < 2:
            logger.warning("데이터 부족 (%d rows): %s", len(series), ticker)
            continue

        latest_close = round(float(series.iloc[-1]), 2)

        # 장중 수익률: 당일 종가 / 당일 시가 - 1
        intraday = None
        if ticker in open_.columns:
            open_series = open_[ticker].dropna()
            open_series = open_series[open_series.index.normalize() <= target_date]
            if len(open_series) >= 1:
                latest_open = float(open_series.iloc[-1])
                if latest_open > 0:
                    intraday = round((latest_close / latest_open - 1) * 100, 2)

        # 폴백: 아시아 장 마감 직후엔 yfinance 일봉의 당일 Open이 NaN으로 와서
        # intraday가 비는 경우가 잦다. 오늘자 수집이면 fast_info의 당일 시가/현재가로 보정한다.
        if intraday is None and is_today:
            fo = fi_opens.get(ticker)
            fl = fi_lasts.get(ticker)
            if fo and fl and fo > 0:
                intraday = round((fl / fo - 1) * 100, 2)

        def calc_return(n: int) -> float | None:
            if len(series) > n:
                past = float(series.iloc[-(n + 1)])
                if past > 0:
                    return round((latest_close - past) / past * 100, 2)
            return None

        daily   = calc_return(1)
        weekly  = calc_return(5)
        monthly = calc_return(21)
        yearly  = calc_return(252)

        # 히트맵 사이즈용 USD 환산 시가총액 (통화 혼합 시 비교 정규화)
        cap = market_caps.get(ticker)
        cur = currencies.get(ticker)
        cap_usd = int(cap * fx[cur]) if (cap and cur and cur in fx) else None

        rows[ticker] = {
            "ticker": ticker, "name": ticker_to_name.get(ticker, ticker),
            "close": latest_close, "market_cap": cap, "market_cap_usd": cap_usd,
            "currency": cur, "intraday_return": intraday, "daily_return": daily,
            "weekly_return": weekly, "monthly_return": monthly, "yearly_return": yearly,
        }

        logger.info(
            "%-6s | 종가=$%8.2f | 장중=%+6.2f%% | 일간=%+6.2f%% | 주간=%+6.2f%% | 월간=%+6.2f%% | 연간=%+6.2f%%",
            ticker, latest_close,
            intraday or 0.0,
            daily    or 0.0,
            weekly   or 0.0,
            monthly  or 0.0,
            yearly   or 0.0,
        )

    store.write_prices(market, date_str, rows)
    logger.info("주가 저장 완료: %s %s %d종목", market, date_str, len(rows))


# ── 메인 ─────────────────────────────────────────────────────

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_args(argv: list[str]) -> tuple[str, str | None]:
    """argv → (country, date_str|None). 인자 순서 무관, 구버전(날짜만) 호환."""
    country = "us"
    date_str = None
    for arg in argv:
        a = arg.strip().lower()
        if a in COUNTRY_TZ:
            country = a
        elif DATE_RE.match(arg.strip()):
            date_str = arg.strip()
    return country, date_str


def main() -> None:
    country, date_str = parse_args(sys.argv[1:])

    # 날짜 결정 (인자 우선 → 해당 국가 타임존 오늘)
    tz = pytz.timezone(COUNTRY_TZ[country])
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    if date_str:
        logger.info("[%s] 지정 날짜 사용: %s", country.upper(), date_str)
    else:
        date_str = today_str
        logger.info("[%s] %s 기준 오늘 날짜: %s", country.upper(), COUNTRY_TZ[country], date_str)
    is_today = (date_str == today_str)

    fetch_and_store(date_str, country, is_today)
    logger.info("=== [%s] 완료 ===", country.upper())


if __name__ == "__main__":
    main()
