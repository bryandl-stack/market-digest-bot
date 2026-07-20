# market-digest-bot

텔레그램 증권 채널을 크롤링해 미국/유럽/일본/한국 시장의 뉴스·주가·매크로·경제캘린더 데이터를 모으고, 이를 바탕으로 한국어 시장 다이제스트를 작성해 텔레그램 봇으로 전송하는 도구입니다. Firebase 등 외부 DB 없이 로컬 JSON 파일(`data/`)만으로 동작합니다.

## 아키텍처

크롤러(`crawlers/*.py`)가 `data/*.json`(`.jsonl`)에 데이터를 쌓고 → `digest.py dump`가 이를 사람이 읽을 수 있는 텍스트로 합쳐 출력 → 이 텍스트를 바탕으로 한국어 요약을 작성해 `digest.py send`로 텔레그램 전송합니다. 저장/조회 계층은 `store.py`(데이터), 설정 로드 계층은 `config_loader.py`(`config/*.json`)로 분리되어 있습니다.

## 설치

```bash
pip install -r requirements.txt
```

## 환경변수 설정 (.env)

```bash
cp .env.example .env
```

`.env`에 아래 키를 채웁니다:

| 키 | 발급처 | 비고 |
|---|---|---|
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | [my.telegram.org](https://my.telegram.org) | 텔레그램 유저 세션(크롤러용) 발급 |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) | 다이제스트 전송용 봇 생성 후 토큰 발급 |
| `TELEGRAM_CHAT_ID` | 봇에게 먼저 메시지(또는 그룹에 초대 후 발화)를 보낸 뒤 `python3 digest.py chatid` 실행 | 위 명령이 최근 chat_id 후보를 출력합니다 |
| `FRED_API_KEY` (선택) | [fred.stlouisfed.org](https://fred.stlouisfed.org) | 없어도 동작함 — 없으면 캘린더의 FRED 발표 예정 경제지표만 스킵되고, 매크로 시세·실적 캘린더·ForexFactory 경제캘린더는 정상 수집됩니다 |

## 설정 파일 (config/*.json)

```bash
cp config/universe.sample.json config/universe.json
cp config/keywords.sample.json config/keywords.json
cp config/channels.sample.json config/channels.json
```

- `config/universe.json`: 추적할 종목 목록(국가별 섹터 → 종목 `ticker`/`nameKr`/`nameEn`).
- `config/keywords.json`: 종목별 뉴스 매칭용 키워드/별칭(쉼표 구분).
- `config/channels.json`: 크롤링할 텔레그램 채널 username 목록.

## 최초 1회: 텔레그램 로그인

```bash
python3 telegram_auth.py
```

전화번호·인증코드(필요 시 2단계 비밀번호)를 입력하면 `telegram_session.session` 파일이 생성됩니다. 이후 크롤러는 이 세션을 재사용합니다.

## 크롤러 실행

```bash
python3 crawlers/crawl_telegram.py morning --countries=us,eu,jp,kr
python3 crawlers/fetch_prices.py us   # 필요한 시장 각각: us eu jp kr
python3 crawlers/fetch_prices.py eu
python3 crawlers/fetch_prices.py jp
python3 crawlers/fetch_prices.py kr
python3 crawlers/fetch_macro_calendar.py
```

`crawl_telegram.py`의 모드는 `morning`/`evening1`/`evening2`/`t0900`/`t1200`/`t1530`/`t2100` 중 하나입니다.

## 다이제스트 생성 및 전송

```bash
python3 digest.py dump
```

출력된 데이터를 바탕으로 한국어 요약을 작성해 `logs/digest_out.txt`에 저장한 뒤:

```bash
python3 digest.py send logs/digest_out.txt
```

요약 작성 규칙(5개 섹션 구성, 서식 규칙 등)은 `.claude/skills/market-digest/SKILL.md`에 정의되어 있으며, [Claude Code](https://claude.com/claude-code) 등 에이전트가 이 스킬을 참고해 덤프 → 요약 → 저장 → 전송까지 수행하도록 만들어졌습니다. 요약 언어는 기본 한국어이며, 다른 언어로 바꾸려면 `SKILL.md`의 3단계 지시문을 원하는 언어로 수정하면 됩니다.

## cron 자동 실행

`run_digest.sh`가 크롤러 실행 후 `claude -p`로 스킬을 호출해 요약·전송까지 수행하는 래퍼입니다.

```bash
crontab -e
# 예: 매일 08:10 KST(전날 23:10 UTC)에 실행
10 23 * * * /path/to/market-digest-bot/run_digest.sh
```

실행 로그는 `logs/digest.log`에 남습니다.
