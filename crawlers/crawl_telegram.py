#!/usr/bin/env python3
"""
Telegram 채널 크롤러 — 종목 언급 뉴스를 로컬 파일(comments)에 자동 저장

사용법:
  python3 crawlers/crawl_telegram.py morning   # 08:00 KST: 전날 22:00 ~ 오늘 08:00
  python3 crawlers/crawl_telegram.py evening1  # 15:40 KST: 오늘 08:00 ~ 오늘 15:40
  python3 crawlers/crawl_telegram.py evening2  # 22:00 KST: 오늘 15:40 ~ 오늘 22:00

cron 등록 (UTC 기준, 예시 경로는 레포 루트 기준):
  0 23 * * *  python3 /path/to/market-digest-bot/crawlers/crawl_telegram.py morning  >> /path/to/market-digest-bot/logs/digest.log 2>&1
  40 6 * * *  python3 /path/to/market-digest-bot/crawlers/crawl_telegram.py evening1 >> /path/to/market-digest-bot/logs/digest.log 2>&1
  0 13 * * *  python3 /path/to/market-digest-bot/crawlers/crawl_telegram.py evening2 >> /path/to/market-digest-bot/logs/digest.log 2>&1
"""

import asyncio
import fcntl
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta

import pytz
from telethon import TelegramClient

import importance as imp

from telegram_config import API_ID, API_HASH

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import store
import config_loader

# ── 상수 ──────────────────────────────────────────────────────────
KST          = pytz.timezone('Asia/Seoul')
SESSION_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "telegram_session")
LOCK_PATH    = SESSION_PATH + '.lock'   # 동시 실행 방지용 파일 락
LOCK_TIMEOUT = 600                       # 락 대기 최대 시간(초)
HEADLINE_MAX = 300
TEXT_MAX     = 3000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ── 시간 범위 계산 ─────────────────────────────────────────────────
def next_monday(d) -> str:
    """주말이면 다음 월요일, 평일이면 그대로 반환"""
    days_ahead = (7 - d.weekday()) % 7  # 0=월 … 6=일
    if d.weekday() == 5:   # 토요일 → +2
        return str(d + timedelta(days=2))
    elif d.weekday() == 6: # 일요일 → +1
        return str(d + timedelta(days=1))
    return str(d)


def get_time_range(mode: str, ref_date=None):
    from datetime import date as date_type
    today = ref_date if isinstance(ref_date, date_type) else datetime.now(KST).date()

    if mode == 'morning':
        # 전날 22:00 KST ~ 오늘 08:00 KST → 날짜는 전일 기준
        end   = KST.localize(datetime(today.year, today.month, today.day, 8, 0, 0))
        start = end - timedelta(hours=10)
        date_str = next_monday(today - timedelta(days=1))
    elif mode == 'evening1':
        # 오늘 08:00 KST ~ 오늘 15:40 KST
        start = KST.localize(datetime(today.year, today.month, today.day, 8, 0, 0))
        end   = KST.localize(datetime(today.year, today.month, today.day, 15, 40, 0))
        date_str = next_monday(today)
    elif mode == 'evening2':
        # 오늘 15:40 KST ~ 오늘 22:00 KST
        start = KST.localize(datetime(today.year, today.month, today.day, 15, 40, 0))
        end   = KST.localize(datetime(today.year, today.month, today.day, 22, 0, 0))
        date_str = next_monday(today)
    # ── 일본·한국 전용 4개 시점 윈도우 (KST 기준) ──────────────
    elif mode == 't0900':
        # 전날 21:00 KST ~ 오늘 09:00 KST (장 시작 전 야간)
        end   = KST.localize(datetime(today.year, today.month, today.day, 9, 0, 0))
        start = end - timedelta(hours=12)
        date_str = next_monday(today)
    elif mode == 't1200':
        # 오늘 09:00 ~ 12:00 KST
        start = KST.localize(datetime(today.year, today.month, today.day, 9, 0, 0))
        end   = KST.localize(datetime(today.year, today.month, today.day, 12, 0, 0))
        date_str = next_monday(today)
    elif mode == 't1530':
        # 오늘 12:00 ~ 15:30 KST
        start = KST.localize(datetime(today.year, today.month, today.day, 12, 0, 0))
        end   = KST.localize(datetime(today.year, today.month, today.day, 15, 30, 0))
        date_str = next_monday(today)
    elif mode == 't2100':
        # 오늘 15:30 ~ 21:00 KST
        start = KST.localize(datetime(today.year, today.month, today.day, 15, 30, 0))
        end   = KST.localize(datetime(today.year, today.month, today.day, 21, 0, 0))
        date_str = next_monday(today)
    else:
        raise ValueError(f"알 수 없는 모드: {mode}")
    return start, end, date_str


# ── 이모티콘 전용 판별 ─────────────────────────────────────────────
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F004\U0001F0CF"
    "\U0001F1E0-\U0001F1FF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "]+",
    flags=re.UNICODE,
)

def is_emoji_only(text: str) -> bool:
    return bool(text.strip()) and not _EMOJI_RE.sub('', text).strip()


# ── 메시지 인기지표(engagement) ────────────────────────────────────
def reaction_total(msg) -> int:
    """메시지 이모지 반응 수 총합 (없으면 0)."""
    r = getattr(msg, 'reactions', None)
    if not r or not getattr(r, 'results', None):
        return 0
    return sum(getattr(x, 'count', 0) for x in r.results)


# ── 마크다운 기호 제거 ─────────────────────────────────────────────
def strip_markdown(text: str) -> str:
    """텔레그램 마크다운 기호 제거 (**bold**, __italic__, ~~strike~~, `code`)"""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'__(.+?)__',     r'\1', text, flags=re.DOTALL)
    text = re.sub(r'~~(.+?)~~',     r'\1', text, flags=re.DOTALL)
    text = re.sub(r'`(.+?)`',       r'\1', text, flags=re.DOTALL)
    text = re.sub(r'\n{2,}',        '\n',  text)  # 연속 줄바꿈 → 1개로
    return text


# ── 헤드라인 추출 ──────────────────────────────────────────────────
MIN_HEADLINE_WORDS = 2   # 첫 문장이 이보다 단어 수가 적으면(한 단어 이하) 다음 문장을 이어붙인다


def _iter_sentences(text: str):
    """유효한 줄을 순회하며 마침표(뒤에 공백/끝) 단위 문장 조각을 순서대로 yield.
    빈/이모티콘만인 조각은 건너뛴다."""
    for line in text.split('\n'):
        line = line.strip()
        if not line or is_emoji_only(line):
            continue
        # 단일 대문자 이니셜 뒤 마침표(예: '도널드 J. 트럼프')에서는 끊지 않는다.
        for part in re.split(r'(?<![A-Z])\.(?:\s|$)', line):
            part = part.strip()
            if not part or is_emoji_only(part):
                continue
            yield part


def extract_headline(text: str) -> str:
    """첫 유효 문장을 헤드라인으로 사용하되, 너무 짧으면(한 단어 이하) 다음 문장을
    이어붙여 의미 있는 헤드라인을 만든다. 최대 HEADLINE_MAX자."""
    headline = ""
    for sentence in _iter_sentences(text):
        headline = sentence if not headline else f"{headline} {sentence}"
        if len(headline) >= HEADLINE_MAX:
            break
        if len(headline.split()) >= MIN_HEADLINE_WORDS:
            break
    if headline:
        return headline[:HEADLINE_MAX]
    return text.strip()[:HEADLINE_MAX]


# ── 본문 구성 ──────────────────────────────────────────────────────
def _strip_prefix(text: str, prefix: str):
    """text 앞부분이 prefix와 (공백·마침표 차이를 무시하고) 일치하면 그 뒤 잔여 문자열을
    반환, 아니면 None. 헤드라인이 여러 문장을 이어붙여 만들어졌을 때도 본문에서 제거하기 위함."""
    skip = lambda ch: ch in " \t\n."
    i = j = 0
    while j < len(prefix):
        if skip(prefix[j]):
            j += 1
            continue
        if i < len(text) and skip(text[i]):
            i += 1
            continue
        if i >= len(text) or text[i] != prefix[j]:
            return None
        i += 1
        j += 1
    return text[i:]


def build_body(full_text: str, headline: str) -> str:
    """헤드라인을 제외한 순수 본문 반환. 최대 TEXT_MAX자."""
    remaining = full_text
    if headline:
        stripped = _strip_prefix(remaining, headline)
        if stripped is not None:
            remaining = stripped.lstrip('\n. ')
    remaining = remaining.strip()
    if len(remaining) > TEXT_MAX:
        remaining = remaining[:TEXT_MAX] + '...'
    return remaining


# ── Jaccard 유사도 중복 체크 ───────────────────────────────────────
JACCARD_THRESHOLD = 0.7

def jaccard_similarity(a: str, b: str) -> float:
    def tokenize(text):
        tokens = re.split(r'[\s\.,\!\?\:\;\-\(\)\[\]\"\'$*#]+', text.lower())
        return set(t for t in tokens if t)
    sa, sb = tokenize(a), tokenize(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)

def is_similar_headline(headline: str, seen_headlines: list) -> bool:
    """저장된 헤드라인 목록과 비교해 유사도가 임계값 이상이면 True 반환"""
    for h in seen_headlines:
        if jaccard_similarity(headline, h) >= JACCARD_THRESHOLD:
            return True
    return False


# ── 종목명 매칭 ────────────────────────────────────────────────────
def _hits_in_headline(name: str, info: dict, text: str) -> bool:
    """헤드라인도 본문과 동일한 경계 규칙으로 매칭 (오탐 방지).
    한글명은 앞 경계만(조사 허용), 영문명·티커는 양쪽 단어경계."""
    return _hits_in_body(name, info, text)


def _hits_in_body(name: str, info: dict, text: str) -> bool:
    """본문용: 앞뒤 경계 조건을 엄격히 검사."""
    name_type = info.get('name_type', 'kr')
    if name_type == 'kr':
        name_hit = bool(re.search(rf'(?<![가-힣]){re.escape(name)}', text))
    else:
        name_hit = bool(re.search(
            rf'(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])',
            text, re.IGNORECASE
        ))
    ticker = info['ticker']
    ticker_hit = (len(ticker) >= 2) and bool(re.search(rf'\b{re.escape(ticker)}\b', text))
    return name_hit or ticker_hit


# URL/도메인 안의 종목명 오탐 방지: 매칭 직전 URL을 제거한다.
# (예: 'news.naver.com' 의 'naver' 가 NAVER 로 오태깅되던 문제)
# TLD 앵커를 둬 '3.5조', 'U.S.' 같은 일반 점 표기는 건드리지 않는다.
_URL_RE = re.compile(
    r'https?://\S+'
    r'|\b[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|io|co\.kr|kr|gov|edu|biz|info|news|tv|me)\b\S*',
    re.IGNORECASE,
)

def _strip_urls(text: str) -> str:
    return _URL_RE.sub(' ', text)


def find_matched_stocks(headline: str, body: str, name_to_info: dict) -> list:
    """헤드라인 우선 탐색(느슨). 헤드라인에 하나라도 매칭되면 본문 탐색 전체 스킵.
    헤드라인 매칭 없을 때만 본문 전체를 엄격 탐색.
    티커가 1글자인 경우 오탐 방지를 위해 티커 매칭에서 제외.
    URL 안의 도메인 토큰이 종목명으로 오인되지 않도록 매칭 전 URL을 제거한다."""
    headline = _strip_urls(headline)
    body     = _strip_urls(body)
    seen    = set()
    matched = []
    for name, info in name_to_info.items():
        ticker = info['ticker']
        if ticker in seen:
            continue
        if _hits_in_headline(name, info, headline):
            seen.add(ticker)
            matched.append(info)

    if matched:
        return matched

    for name, info in name_to_info.items():
        ticker = info['ticker']
        if ticker in seen:
            continue
        if _hits_in_body(name, info, body):
            seen.add(ticker)
            matched.append(info)
    return matched


def score_payloads(payloads, prior_scores):
    """payload 리스트에 importanceScore/Tier/Signals를 채운다.
    각 payload는 author/headline/text/forwards/views/reactions/_terms 를 갖는다.
    _terms(매칭 종목명 집합)는 점수 계산 후 제거한다."""
    dist = imp.build_channel_distributions(payloads)
    for p in payloads:
        fields = imp.build_importance(
            p.get('headline', ''), p.get('text', ''), p.get('author', ''),
            p.get('forwards', 0), p.get('views', 0), p.get('reactions', 0),
            p.pop('_terms', set()), dist, has_popularity=True, repeat_count=1)
        p.update(fields)
    imp.finalize_tiers(payloads, prior_scores)


def load_trailing_scores(date_str, days=7):
    """최근 days일(date_str 포함)의 importanceScore 목록 — 5단계 등급 백분위 풀.
    한 번 실행분이 작아도 넓은 분포로 등급을 매겨 안정화한다."""
    base = datetime.strptime(date_str, "%Y-%m-%d")
    dates = [(base - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(0, days + 1)]
    return [float(c.get("importanceScore", 0) or 0)
            for c in store.read_comments(dates) if c.get("importanceScore") is not None]


# ── 메인 크롤러 ────────────────────────────────────────────────────
async def crawl(mode: str, ref_date=None, countries=None):
    start, end, date_str = get_time_range(mode, ref_date)
    countries = countries or ['us', 'eu', 'jp', 'kr']
    logger.info("=== 크롤링 시작 | 모드: %s | 국가: %s | %s ~ %s | 기준일: %s ===",
                mode, ','.join(countries),
                start.strftime('%Y-%m-%d %H:%M'), end.strftime('%Y-%m-%d %H:%M'), date_str)

    # 섹터·종목·키워드·채널 로드 (로컬 config)
    name_to_info, _ticker_to_name, _ticker_country = config_loader.load_universe(countries)
    name_to_info = config_loader.load_keywords(name_to_info)
    channels = config_loader.load_channels()
    logger.info("종목명 %d개, 채널 %d개 로드", len(name_to_info), len(channels))

    # ticker → 매칭 후보 용어(멘션 횟수 계산용)
    ticker_to_terms = {}
    for nm, info in name_to_info.items():
        ticker_to_terms.setdefault(info['ticker'], set()).add(nm)

    # Telethon 클라이언트
    client = TelegramClient(SESSION_PATH, int(API_ID), API_HASH)
    await client.start()

    # ── 배치 처리를 위한 기존 데이터 1회 로드 ────────────────────────
    seen_links:     set[str]  = store.existing_links(date_str)
    seen_headlines: list[str] = store.existing_headlines(date_str)
    logger.info("기존 데이터 로드: 링크 %d개, 헤드라인 %d개", len(seen_links), len(seen_headlines))

    # ── 전 채널 메시지 수집 (메모리 내 필터링) ────────────────────────
    payloads = []  # 최종 저장 대상

    for channel in channels:
        logger.info("--- 채널: @%s ---", channel)
        try:
            entity = await client.get_entity(channel)

            messages = []
            async for msg in client.iter_messages(entity, offset_date=end.astimezone(pytz.utc)):
                msg_time = msg.date.astimezone(KST)
                if msg_time < start:
                    break
                text = strip_markdown((msg.text or '').strip())
                if not text:
                    continue
                messages.append((msg, msg_time, text))

            messages.sort(key=lambda x: x[1])
            logger.info("  수집: %d개 메시지", len(messages))

            for msg, msg_time, text in messages:
                tg_link  = f"https://t.me/{channel}/{msg.id}"
                headline = extract_headline(text)
                body     = build_body(text, headline)
                matched  = find_matched_stocks(headline, body, name_to_info)
                if not matched:
                    continue

                if imp.is_promo(headline + ' ' + body):
                    logger.info("  홍보성 skip: %s", headline[:60])
                    continue

                # 중복 체크 1: 동일 링크 (메모리)
                if tg_link in seen_links:
                    logger.info("  중복 skip (링크): %s", tg_link)
                    continue

                # 중복 체크 2: Jaccard 유사도 (메모리)
                if is_similar_headline(headline, seen_headlines):
                    logger.info("  중복 skip (유사 헤드라인): %s", headline[:60])
                    continue

                sector_map: dict[str, list] = {}
                for info in matched:
                    sector_map.setdefault(info['sector_id'], []).append(info)

                sector_ids  = list(sector_map.keys())
                tickers_map = {
                    sid: [info['ticker'] for info in infos]
                    for sid, infos in sector_map.items()
                }

                payloads.append({
                    'sectorIds': sector_ids,
                    'tickers':   tickers_map,
                    'date':      date_str,
                    'author':    f"@{channel}",
                    'uid':       'telegram_crawler',
                    'headline':  headline,
                    'text':      body,
                    'link':      tg_link,
                    'timestamp': msg_time,
                    'tg_link':   tg_link,
                    'forwards':  msg.forwards or 0,
                    'views':     msg.views or 0,
                    'reactions': reaction_total(msg),
                    '_terms':    set().union(
                        *(ticker_to_terms.get(info['ticker'], set()) for info in matched)
                    ),
                })
                seen_links.add(tg_link)
                seen_headlines.append(headline)
                logger.info("  수집 완료: %s → 섹터=%s", tg_link, sector_ids)

        except Exception as exc:
            logger.error("채널 @%s 오류: %s", channel, exc, exc_info=True)

    # ── 중요도 점수·등급 산정 ────────────────────────────────────────
    # 등급은 최근 7일 분포(trailing window) 기준 백분위 → 작은 배치에서도 안정적
    prior_scores = load_trailing_scores(date_str, days=7)
    score_payloads(payloads, prior_scores)

    saved_total = store.append_comments(payloads)
    logger.info("저장 완료: %d개", saved_total)

    await client.disconnect()
    logger.info("=== 완료: 총 %d개 코멘트 저장 ===", saved_total)


def acquire_session_lock(timeout: int = LOCK_TIMEOUT):
    """텔레그램 세션 파일 동시 사용 방지용 배타 락 획득.
    다른 인스턴스가 실행 중이면 timeout까지 대기, 실패 시 None 반환.
    반환된 파일 객체는 프로세스 종료(또는 close) 시 자동 해제됨."""
    fd = open(LOCK_PATH, 'w')
    waited = 0
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            if waited >= timeout:
                logger.error("다른 텔레그램 크롤러가 실행 중 — 락 대기 %ds 초과, 종료", timeout)
                fd.close()
                return None
            if waited == 0:
                logger.info("다른 인스턴스 실행 중 — 세션 락 대기...")
            time.sleep(5)
            waited += 5


VALID_MODES = ('morning', 'evening1', 'evening2', 't0900', 't1200', 't1530', 't2100')

if __name__ == '__main__':
    import re as _re
    # argv 파싱: 모드(필수), 날짜(YYYY-MM-DD, 선택), --countries us,eu (선택)
    mode = None
    ref = None
    countries = None
    from datetime import date as date_type
    for arg in sys.argv[1:]:
        if arg.startswith('--countries'):
            val = arg.split('=', 1)[1] if '=' in arg else None
            if val:
                countries = [c.strip().lower() for c in val.split(',') if c.strip()]
        elif arg in VALID_MODES:
            mode = arg
        elif _re.match(r'^\d{4}-\d{2}-\d{2}$', arg):
            ref = date_type.fromisoformat(arg)
        elif countries is None and ',' in arg and all(p.strip().lower() in ('us', 'eu', 'jp', 'kr') for p in arg.split(',')):
            countries = [c.strip().lower() for c in arg.split(',')]

    if not mode:
        print(f"사용법: python3 crawlers/crawl_telegram.py [{'|'.join(VALID_MODES)}] [YYYY-MM-DD] [--countries us,eu]")
        sys.exit(1)

    # 세션 파일 동시 접근 방지 (다른 인스턴스 종료 대기)
    _lock = acquire_session_lock()
    if _lock is None:
        sys.exit(1)
    try:
        asyncio.run(crawl(mode, ref, countries))
    finally:
        fcntl.flock(_lock, fcntl.LOCK_UN)
        _lock.close()
