#!/bin/bash
# cron 다이제스트 래퍼. 레포 루트 기준 상대경로. claude CLI 로 스킬 호출.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
mkdir -p logs
# (선택) 주말 스킵: 필요 시 아래 3줄 주석 해제
# DOW=$(date +%u); if [ "$DOW" -ge 6 ]; then echo "주말 스킵"; exit 0; fi
python3 crawlers/crawl_telegram.py morning --countries=us,eu,jp,kr >> logs/digest.log 2>&1
for m in us eu jp kr; do
  python3 crawlers/fetch_prices.py "$m" >> logs/digest.log 2>&1
done
python3 crawlers/fetch_macro_calendar.py     >> logs/digest.log 2>&1
claude -p "market-digest 스킬로 오늘 다이제스트를 작성하고 텔레그램으로 전송하라." \
  --allowedTools "Bash(python3 digest.py dump)" "Bash(python3 digest.py send:*)" "Write" \
  >> logs/digest.log 2>&1
