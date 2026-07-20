"""Telegram 유저 세션 자격증명 (channels 목록은 config/channels.json 으로 이동)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _env import load_env  # noqa: E402

load_env()

API_ID = os.environ.get("TELEGRAM_API_ID")
API_HASH = os.environ.get("TELEGRAM_API_HASH")

if not API_ID or not API_HASH:
    raise RuntimeError(
        "TELEGRAM_API_ID / TELEGRAM_API_HASH 가 필요합니다. .env.example 참고.")
