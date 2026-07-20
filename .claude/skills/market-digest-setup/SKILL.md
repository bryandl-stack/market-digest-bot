---
name: market-digest-setup
description: market-digest-bot 최초 세팅 — 키·config(유니버스/채널)·텔레그램 로그인을 대화형으로 준비하고 스모크 테스트한다. 처음 클론했거나 다이제스트가 빈약할 때 사용.
---

# 시장 다이제스트 세팅

사용자가 market-digest-bot을 처음 쓰거나 커버리지를 넓히려 할 때, 아래를 **대화형으로**
함께 준비한다. 각 단계에서 현재 상태를 먼저 확인하고, 이미 된 건 건너뛴다.
사용자에게 한 번에 하나씩 물어보고, 결정이 필요한 지점에서 **제안**을 제시한다.

## 1. 키 (.env)

`.env`가 없으면 `cp .env.example .env`. 아래를 채우도록 안내한다(값은 사용자가 직접 입력):

| 키 | 발급처 |
|---|---|
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | my.telegram.org (유저 세션용) |
| `TELEGRAM_BOT_TOKEN` | @BotFather 로 봇 생성 |
| `TELEGRAM_CHAT_ID` | 봇에게 먼저 아무 메시지나 보낸 뒤 `python3 digest.py chatid` 실행 |
| `FRED_API_KEY` (선택) | fred.stlouisfed.org — 없으면 경제지표만 스킵 |

키는 절대 코드/커밋에 넣지 않는다(`.env`는 gitignore).

## 2. 설정 (config/*.json)

`config/*.json`이 없으면 기본값을 복사한다:
```
cp config/universe.default.json config/universe.json
cp config/keywords.default.json config/keywords.json
cp config/channels.default.json config/channels.json
```
기본 유니버스는 미/유/일/한 ~90개 글로벌 대형주, 기본 채널은 공개 증권 텔레그램 8개다.
그런 다음 대화로 조정한다:

- **관심 시장**: us/eu/jp/kr 중 어디를 볼지 물어, 안 볼 시장은 `universe.json`에서 뺀다.
- **채널**: 현재 `channels.json` 목록을 보여주고, 추가/삭제를 묻는다. 채널은 공개
  채널 username(예: `t.me/<username>` 의 username)만 넣는다. 좋은 채널을 모르면
  기본 8개로 시작하라고 안내한다.
- **커스텀 종목(선택)**: 사용자가 추가하고 싶은 종목이 있으면, yfinance 호환 티커를
  확인해(미국은 심볼 그대로, 유럽/일본/한국은 거래소 접미사 `.PA/.T/.KS` 등) 해당
  시장·섹터의 `stocks`에 `{"ticker","nameKr","nameEn"}` 항목을 추가한다.

`config/*.json`(실제 파일)은 gitignore이므로 개인 커스터마이즈가 공개되지 않는다.

## 3. 텔레그램 로그인 (최초 1회)

`telegram_session.session`이 없으면 사용자에게 직접 실행하도록 안내한다:
```
python3 telegram_auth.py
```
전화번호·인증코드(필요 시 2단계 비밀번호) 입력이 필요해 **대화형이라 에이전트가 대신
실행할 수 없다.** 세션 파일이 생기면 이후 크롤러가 재사용한다.

## 4. 스모크 테스트

세팅이 끝나면 소량으로 한 번 돌려 커버리지를 확인한다:
```
python3 crawlers/crawl_telegram.py morning --countries=us,eu,jp,kr
python3 crawlers/fetch_prices.py us
python3 crawlers/fetch_macro_calendar.py
python3 digest.py dump
```
`dump` 출력을 사용자에게 보여주고 평가한다:
- 뉴스가 비었거나 적으면 → **실행 시각**(morning 윈도우는 아침에 채워짐)과 **채널 수**를
  점검하고, 채널 추가를 제안한다.
- 주가 섹션에 특정 시장이 비면 → 그 시장 `fetch_prices <market>`를 돌렸는지, 유니버스에
  종목이 있는지 확인한다.

## 5. 인계

세팅과 스모크가 정상이면, 실제 요약 작성·전송은 `market-digest` 스킬로 진행하라고
안내한다(크롤 → dump → 한국어 5섹션 요약 → send).
