#!/usr/bin/env python3
"""Telegram 최초 인증 스크립트 — 1회만 실행하면 됩니다."""
import asyncio
import os
import sys
from telethon import TelegramClient

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "crawlers"))
from telegram_config import API_ID, API_HASH

SESSION_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'telegram_session')

async def main():
    client = TelegramClient(SESSION_PATH, int(API_ID), API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"이미 인증됨: {me.first_name} (@{me.username})")
        await client.disconnect()
        return

    phone = input("전화번호 입력 (예: +821012345678): ").strip()
    await client.send_code_request(phone)

    code = input("텔레그램으로 받은 인증 코드 입력: ").strip()
    try:
        await client.sign_in(phone, code)
    except Exception as e:
        pw = input(f"2단계 인증 비밀번호 입력 (없으면 Enter): ").strip()
        if pw:
            await client.sign_in(password=pw)

    me = await client.get_me()
    print(f"\n인증 성공: {me.first_name} (@{me.username})")
    print("telegram_session.session 파일이 저장되었습니다.")
    await client.disconnect()

asyncio.run(main())
