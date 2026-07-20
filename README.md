# market-digest-bot

텔레그램 증권 채널을 크롤링해 **미국·유럽·일본·한국** 시장의 뉴스·주가·매크로·경제캘린더를 모으고, 이를 바탕으로 **한국어 시장 다이제스트**를 작성해 텔레그램 봇으로 매일 전송하는 도구입니다. Firebase 등 외부 DB 없이 **로컬 JSON 파일**(`data/`)만으로 동작하며, 필요한 키는 전부 `.env`로 주입합니다(레포에 개인 키·개인정보 없음).

## 주요 기능

- 📰 **뉴스·증권사 레포트** — 텔레그램 증권 채널을 유저 세션으로 크롤링, 종목 태깅 + 중요도 스코어링(5단계 등급)
- 📈 **주가 등락** — yfinance로 4개 시장 종목의 장중/일간/주간/월간/연간 수익률
- 🌐 **매크로** — 주요 지수·금리·환율·원자재의 전일 대비 변동
- 🗓 **캘린더** — 예정 실적(yfinance) + 경제지표(ForexFactory 스크레이프, FRED 선택)
- 🤖 **자동 요약·전송** — Claude Code 등 에이전트가 스킬을 따라 덤프를 한국어 5섹션으로 요약해 봇으로 전송(cron 무인 실행 가능)

## 다이제스트 예시

```
📈 주가 등락 (2026-07-19 종가)
🇺🇸 미국 — 상승: AIG +3.17%, 웨스턴디지털 +2.23% / 하락: 넷플릭스 -7.26%
🇰🇷 한국 — 상승: SK텔레콤 +5.53%, 기아 +3.24% / 하락: SK하이닉스 -11.53%

📰 핵심 뉴스
· 엔비디아–도요타 제휴 확대, 레벨2++ 자율주행에 엔비디아 반도체·OS 채택 https://t.me/...
· 메타, 앤스로픽과 100억달러 AI 인프라 임대 초기 논의 https://t.me/...

🏦 증권사 레포트
· HSBC | SK하이닉스 상승여력 80%+ | HBM 가격 상승이 강한 AI 수요 방증 https://t.me/...

🌐 매크로 (전일 대비)
S&P500 7,498.75 (+0.01%) · 나스닥 28,828.25 (+0.19%) · 코스피 6,820.60 (-0.67%)

🗓 캘린더
· 7/29 삼성전자 실적 · 7/30 애플 실적, 미국 GDP·PCE 발표
```

## 동작 방식

```
crawlers/*.py  ──►  data/*.json(.jsonl)  ──►  digest.py dump  ──►  (에이전트 요약)  ──►  digest.py send  ──►  텔레그램 봇
   크롤링              로컬 저장                 텍스트 덤프           한국어 5섹션            봇 전송
```

- **저장 계층** `store.py` — 크롤러 산출물을 `data/`에 읽고 쓰는 유일한 창구
- **설정 계층** `config_loader.py` — `config/*.json`(유니버스·키워드·채널)을 로드
- 이 두 계층만 로컬 파일 기반이라, 크롤링·중요도 점수·티커 태깅·봇 전송 로직은 그대로 유지됩니다.

### 레포 구조

```
market-digest-bot/
├── crawlers/
│   ├── crawl_telegram.py        # 텔레그램 채널 크롤 + 종목 태깅 + 중요도 점수 (Telethon)
│   ├── fetch_prices.py          # 주가 등락 (yfinance)
│   ├── fetch_macro_calendar.py  # 매크로 + 캘린더 (yfinance·ForexFactory·FRED)
│   └── importance.py            # 뉴스 중요도 스코어링
├── digest.py                    # dump(로컬 읽어 텍스트) + send(봇 전송) + chatid
├── store.py                     # 로컬 JSON 저장/조회 계층
├── config_loader.py             # config/*.json 로드 계층
├── telegram_auth.py             # 텔레그램 최초 로그인(세션 생성)
├── config/
│   ├── universe.default.json    # 기본 종목 유니버스 (미/유/일/한 ~90종목)
│   ├── keywords.default.json    # 기본 별칭 키워드
│   └── channels.default.json    # 기본 텔레그램 채널
├── .claude/skills/
│   ├── market-digest/           # 실행 스킬 (크롤→덤프→요약→전송)
│   └── market-digest-setup/     # 대화형 세팅 스킬
├── run_digest.sh                # cron 래퍼
├── tests/                       # pytest
├── .env.example
└── requirements.txt
```

## 요구사항

- Python **3.10+** (`X | None` 타입 문법 사용)
- 텔레그램 계정(유저 세션용) + 텔레그램 봇 하나

---

## 빠른 시작

### 1. 설치

```bash
git clone https://github.com/bryandl-stack/market-digest-bot.git
cd market-digest-bot
pip install -r requirements.txt
```

### 2. 키 설정 (.env)

```bash
cp .env.example .env
```

`.env`에 아래 키를 채웁니다:

| 키 | 발급처 | 무엇을 켜는가 |
|---|---|---|
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | [my.telegram.org](https://my.telegram.org) | 뉴스·레포트 크롤 (유저 세션) |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) | 다이제스트 전송 |
| `TELEGRAM_CHAT_ID` | 봇에게 먼저 발화 후 `python3 digest.py chatid` 실행 | 전송 대상 |
| `FRED_API_KEY` *(선택)* | [fred.stlouisfed.org](https://fred.stlouisfed.org) | 캘린더의 FRED 경제지표 |

> 주가·매크로·실적 캘린더·ForexFactory 경제캘린더는 **키가 필요 없습니다.** 텔레그램 키가 없으면 뉴스/레포트 섹션만, 봇 토큰이 없으면 전송만 빠집니다.

### 3. 설정 파일 (config/*.json)

**권장 — 대화형 세팅**: [Claude Code](https://claude.com/claude-code) 등 에이전트에서 `market-digest-setup` 스킬을 실행하면 키·유니버스·채널·텔레그램 로그인을 대화로 안내하고 스모크 테스트까지 해줍니다.

**수동 — 기본값 복사 후 편집**:
```bash
cp config/universe.default.json config/universe.json
cp config/keywords.default.json config/keywords.json
cp config/channels.default.json config/channels.json
```

### 4. 텔레그램 로그인 (최초 1회)

```bash
python3 telegram_auth.py
```
전화번호·인증코드(필요 시 2단계 비밀번호)를 입력하면 `telegram_session.session` 파일이 생성되고, 이후 크롤러가 재사용합니다.

### 5. 크롤 → 덤프 → 전송

```bash
# 크롤 (data/ 채우기)
python3 crawlers/crawl_telegram.py morning --countries=us,eu,jp,kr
for m in us eu jp kr; do python3 crawlers/fetch_prices.py "$m"; done
python3 crawlers/fetch_macro_calendar.py

# 덤프 확인
python3 digest.py dump

# (에이전트가 요약을 logs/digest_out.txt 에 작성) 후 전송
python3 digest.py send logs/digest_out.txt
```

요약 작성은 `market-digest` 스킬을 따르는 에이전트가 수행합니다. 손으로 요약을 써서 `logs/digest_out.txt`에 넣고 `send`만 실행해도 됩니다.

---

## 설정 파일 상세

### `universe.json` — 추적 종목

국가별 → 섹터 → 종목 구조입니다. 유럽·일본·한국 티커는 **yfinance 호환 거래소 접미사**(`.PA`/`.T`/`.KS` 등)를 씁니다.

```json
{
  "us": [
    {"id": "us_semi", "name": "반도체", "stocks": [
      {"ticker": "NVDA", "nameKr": "엔비디아", "nameEn": "NVIDIA"}
    ]}
  ],
  "kr": [
    {"id": "kr_semi", "name": "반도체", "stocks": [
      {"ticker": "005930.KS", "nameKr": "삼성전자", "nameEn": "Samsung Electronics"}
    ]}
  ]
}
```

기본 유니버스는 미(~40)·유(~20)·일(~15)·한(~16) **약 90종목**입니다.

### `keywords.json` — 별칭 (선택)

`{ "티커": "별칭1,별칭2" }` 형식. 유니버스의 `nameKr`/`nameEn`만으로도 태깅되지만, 별칭으로 재현율을 높입니다.

```json
{ "005930.KS": "삼전,삼성", "000660.KS": "하이닉스" }
```

### `channels.json` — 크롤 대상 채널

공개 채널 username 목록입니다(`t.me/<username>`의 username).

```json
["bornlupin", "d_ticker", "aetherjapanresearch"]
```

기본값은 공개 증권 채널 8개입니다(**예시** — 취향껏 교체·추가하세요).

---

## 크롤 모드 (시간 윈도우, KST 기준)

`crawl_telegram.py <mode>`는 아침/저녁 또는 4개 시점 윈도우 중 하나로 메시지를 수집합니다. 하루에 여러 번 돌려 누적할수록 다이제스트가 풍부해집니다.

| 모드 | 수집 구간 | 기준일 |
|---|---|---|
| `morning` | 전날 22:00 ~ 당일 08:00 | 전일 |
| `evening1` | 당일 08:00 ~ 15:40 | 당일 |
| `evening2` | 당일 15:40 ~ 22:00 | 당일 |
| `t0900` | 전날 21:00 ~ 당일 09:00 | 당일 |
| `t1200` | 09:00 ~ 12:00 | 당일 |
| `t1530` | 12:00 ~ 15:30 | 당일 |
| `t2100` | 15:30 ~ 21:00 | 당일 |

> **아침에 실행하세요.** `morning` 윈도우는 당일 08:00까지라, 새벽에 돌리면 이후 올라올 미국 장마감 뉴스·증권사 레포트를 아직 못 긁습니다.

## 데이터 저장 구조

크롤러 산출물은 모두 `data/`(gitignore)에 쌓입니다.

```
data/
├── comments/<date>.jsonl     # 뉴스·레포트 코멘트 (종목·중요도 태깅)
├── prices/<market>/<date>.json  # 시장별 주가 등락
├── macro_1d.json             # 매크로 시세
└── calendar.json             # 예정 경제지표 + 실적
```

## 자동화 (cron)

`run_digest.sh`가 크롤러 실행 후 `claude -p`로 `market-digest` 스킬을 호출해 요약·전송까지 수행합니다.

```bash
crontab -e
# 예: 매일 08:10 KST(전날 23:10 UTC)에 실행
10 23 * * * /path/to/market-digest-bot/run_digest.sh
```

실행 로그는 `logs/digest.log`에 남습니다.

## 요약 커스터마이즈

요약 규칙(5개 섹션 구성·서식)은 `.claude/skills/market-digest/SKILL.md`에 정의돼 있습니다. **요약 언어는 기본 한국어**이며, 다른 언어로 바꾸려면 `SKILL.md`의 3단계 지시문을 원하는 언어로 수정하면 됩니다.

## 테스트

```bash
python3 -m pytest -q
```

## 문제 해결

| 증상 | 원인·해결 |
|---|---|
| 뉴스 섹션이 비거나 적음 | **실행 시각**(아침에 돌렸는지)과 **채널 수**를 점검. 유니버스에 없는 종목의 뉴스는 태깅 안 돼 버려집니다 — 관심 종목을 유니버스에 추가하세요. |
| 특정 시장 주가가 빔 | 그 시장 `fetch_prices <market>`를 돌렸는지, 유니버스에 해당 시장 종목이 있는지 확인. |
| 캘린더에 경제지표가 없음 | `FRED_API_KEY` 미설정(선택 키). 없어도 실적·ForexFactory 지표는 나옵니다. |
| `telegram_auth`가 다시 로그인 요구 | `telegram_session.session`이 없거나 만료됨 — 다시 `python3 telegram_auth.py` 실행. |
| 다이제스트가 전반적으로 빈약 | 기본 유니버스·채널은 최소 시작점입니다. 커버리지를 넓히려면 유니버스·채널을 확장하세요(`market-digest-setup` 스킬이 도와줍니다). |

## 개인정보·보안

- `.env`, `*.session`, `data/`, `logs/`, 실제 `config/*.json`은 **gitignore**입니다 — 개인 키·세션·커스터마이즈가 공개되지 않습니다.
- 레포에 커밋되는 건 `config/*.default.json`(예시 기본값)뿐입니다.
