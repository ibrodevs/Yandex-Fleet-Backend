from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl


class MiniAppAuthError(ValueError):
    pass


def validate_telegram_init_data(
    init_data: str,
    *,
    bot_token: str,
    max_age_seconds: int = 86_400,
) -> dict[str, Any]:
    if not init_data:
        raise MiniAppAuthError("Telegram initData отсутствует.")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise MiniAppAuthError("В initData отсутствует hash.")

    data_check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(pairs.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise MiniAppAuthError("Некорректная подпись Telegram initData.")

    auth_date_raw = pairs.get("auth_date")
    if auth_date_raw:
        try:
            auth_date = int(auth_date_raw)
        except ValueError as exc:
            raise MiniAppAuthError("Некорректный auth_date.") from exc
        if abs(int(time.time()) - auth_date) > max_age_seconds:
            raise MiniAppAuthError("Telegram initData устарел.")

    user_raw = pairs.get("user")
    if not user_raw:
        raise MiniAppAuthError("В initData отсутствует пользователь.")

    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise MiniAppAuthError("Некорректные данные пользователя.") from exc

    if not isinstance(user, dict) or not user.get("id"):
        raise MiniAppAuthError("Некорректный Telegram пользователь.")

    return user
