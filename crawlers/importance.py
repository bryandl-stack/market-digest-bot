#!/usr/bin/env python3
"""뉴스/텔레그램 코멘트 중요도 점수 산정 (순수 함수, 외부 의존성 없음).

채점식(B2):
  popularity 0.55 (forwards .7 / views .2 / reactions .1, 채널 백분위 정규화)
  event      0.25 (이벤트 키워드 매칭 시 1.0)
  mention    0.20 (헤드라인 2배 가중, min(raw,6)/6)
  등급: trailing 점수 분포의 백분위 (상위 15% high / 다음 35% medium / 나머지 low)
"""
import bisect
import re

# ── 가중치 ────────────────────────────────────────────────────────
W_POP, W_EVENT, W_MENTION = 0.55, 0.25, 0.20
POP_F, POP_V, POP_R = 0.7, 0.2, 0.1   # popularity 내부 비중

# 뉴스 전용 가중치 — popularity가 없으므로 매체 권위도가 그 자리의 독립 신호 역할.
W_SRC_NEWS, W_EVENT_NEWS, W_MENTION_NEWS = 0.35, 0.40, 0.25

# ── 이벤트 키워드 (한/영) ─────────────────────────────────────────
EVENT_KWS = [
    '실적', '어닝', 'earnings', 'guidance', '가이던스', '전망', '목표주가',
    '목표 주가', 'target price', '인수', '합병', 'm&a', 'merger', 'acquisition',
    '지분', '소송', 'lawsuit', 'fda', '승인', 'approval', '리콜', 'recall',
    '상향', '하향', 'upgrade', 'downgrade', '파산', 'bankruptcy', '배당',
    'dividend', '계약', '수주', '신고가', '급등', '급락', '규제', '제재', '특허',
]
_EVENT_RE = re.compile('|'.join(re.escape(k) for k in EVENT_KWS), re.IGNORECASE)


def build_channel_distributions(rows):
    """rows({'author','forwards','views','reactions'}) → 채널별 정렬된 분포."""
    by_ch = {}
    for r in rows:
        d = by_ch.setdefault(r.get('author'), {'forwards': [], 'views': [], 'reactions': []})
        d['forwards'].append(r.get('forwards', 0) or 0)
        d['views'].append(r.get('views', 0) or 0)
        d['reactions'].append(r.get('reactions', 0) or 0)
    for d in by_ch.values():
        for k in d:
            d[k].sort()
    return by_ch


def _pctl(sorted_vals, v):
    if not sorted_vals:
        return 0.0
    return bisect.bisect_right(sorted_vals, v) / len(sorted_vals)


def popularity_subscore(author, forwards, views, reactions, dist):
    d = dist.get(author)
    if not d:
        return 0.0
    return (POP_F * _pctl(d['forwards'], forwards or 0)
            + POP_V * _pctl(d['views'], views or 0)
            + POP_R * _pctl(d['reactions'], reactions or 0))


def mention_raw(headline, body, terms):
    """매칭된 종목명/키워드 등장 횟수. 헤드라인 2배 가중, 2글자 미만 term 제외."""
    raw = 0
    for term in terms:
        if not term or len(term) < 2:
            continue
        pat = re.compile(rf'(?<![A-Za-z0-9가-힣]){re.escape(term)}(?![A-Za-z0-9])', re.IGNORECASE)
        raw += 2 * len(pat.findall(headline or '')) + len(pat.findall(body or ''))
    return raw


def event_keywords(text):
    return sorted(set(m.group(0) for m in _EVENT_RE.finditer(text or '')))


def compute_score(popularity, event_hit, mention_raw_v, has_popularity=True, source_score=0.0):
    s_event = 1.0 if event_hit else 0.0
    s_mention = min(mention_raw_v, 6) / 6
    if has_popularity:
        num = W_POP * popularity + W_EVENT * s_event + W_MENTION * s_mention
        den = W_POP + W_EVENT + W_MENTION
    else:
        # 뉴스: popularity 대신 매체 권위도(source_score)를 독립 신호로 사용.
        num = W_SRC_NEWS * source_score + W_EVENT_NEWS * s_event + W_MENTION_NEWS * s_mention
        den = W_SRC_NEWS + W_EVENT_NEWS + W_MENTION_NEWS
    return round(100 * num / den, 1)


# 5단계 등급: 균등 5분위(각 20%). trailing 분포의 p80/p60/p40/p20 경계.
TIER_LABELS = ('very_high', 'high', 'medium', 'low', 'very_low')
TIER_PCTL   = (0.80, 0.60, 0.40, 0.20)


def tier_cutoffs(scores):
    """trailing 점수 분포 → (p80, p60, p40, p20) 경계. 데이터 없으면 점수 자체 기준 폴백."""
    s = sorted(scores)
    n = len(s)
    if n == 0:
        return (80.0, 60.0, 40.0, 20.0)
    return tuple(s[min(int(q * n), n - 1)] for q in TIER_PCTL)


def assign_tier(score, cutoffs):
    """점수와 경계(상위→하위 정렬) → 5단계 라벨."""
    for i, cut in enumerate(cutoffs):
        if score >= cut:
            return TIER_LABELS[i]
    return TIER_LABELS[-1]


# ── 홍보성/저품질 글 필터 ─────────────────────────────────────────
# 수익 인증·리딩방·무료 추천 등 정보가치 낮은 홍보성 글 패턴.
_PROMO_RES = [
    re.compile(r'\d+\s*배\s*(?:수익|먹|벌)', re.IGNORECASE),
    re.compile(r'\d+\s*%\s*수익', re.IGNORECASE),
    re.compile(r'수익\s*인증', re.IGNORECASE),
    re.compile(r'리딩방', re.IGNORECASE),
    re.compile(r'무료\s*(?:추천|리딩|입장)', re.IGNORECASE),
]


def is_promo(text):
    t = text or ''
    return any(rx.search(t) for rx in _PROMO_RES)


def repeat_boost(repeat_count):
    """같은 런에서 서로 다른 채널/소스가 동일 스토리를 실으면 소폭 가점(0–8점)."""
    return round(8.0 * min(max(repeat_count - 1, 0), 3) / 3, 1)


def build_importance(headline, body, author, forwards, views, reactions,
                     terms, dist, has_popularity=True, repeat_count=1, source_score=0.0):
    pop = popularity_subscore(author, forwards, views, reactions, dist) if has_popularity else 0.0
    evs = event_keywords((headline or '') + ' ' + (body or ''))
    mraw = mention_raw(headline, body, terms)
    base = compute_score(pop, bool(evs), mraw, has_popularity=has_popularity, source_score=source_score)
    boost = repeat_boost(repeat_count)
    score = min(100.0, round(base + boost, 1))
    signals = {
        'popularity': round(pop, 3),
        'forwards': forwards or 0,
        'views': views or 0,
        'reactions': reactions or 0,
        'mentionCount': mraw,
        'eventKeywords': evs,
        'repeatBoost': boost,
    }
    if not has_popularity:
        for k in ('popularity', 'forwards', 'views', 'reactions'):
            signals.pop(k, None)
        signals['sourceAuthority'] = round(source_score, 2)
    return {'importanceScore': score, 'importanceSignals': signals}


def finalize_tiers(payloads, prior_scores):
    """payloads 각 항목에 importanceTier를 in-place로 채운다."""
    scores = list(prior_scores) + [p['importanceScore'] for p in payloads]
    cutoffs = tier_cutoffs(scores)
    for p in payloads:
        p['importanceTier'] = assign_tier(p['importanceScore'], cutoffs)
