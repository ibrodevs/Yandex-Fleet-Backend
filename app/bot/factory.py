from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode


def create_bot(
    token: str,
    *,
    http_proxy: str | None = None,
) -> Bot:
    session = None
    if http_proxy:
        session = AiohttpSession(proxy=http_proxy)

    return Bot(
        token=token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
