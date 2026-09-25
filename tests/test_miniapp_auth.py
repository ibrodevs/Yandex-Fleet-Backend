import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.miniapp.auth import MiniAppAuthError, validate_telegram_init_data


def _signed_init_data(token: str) -> str:
    pairs = {
        "auth_date": str(int(time.time())),
        "query_id": "AAE-test-query",
        "user": json.dumps(
            {
                "id": 123456789,
                "first_name": "Test",
                "username": "demo",
            },
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(pairs.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        token.encode(),
        hashlib.sha256,
    ).digest()
    pairs["hash"] = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(pairs)


def test_validate_telegram_init_data():
    token = "123456:TEST_TOKEN"
    user = validate_telegram_init_data(
        _signed_init_data(token),
        bot_token=token,
    )
    assert user["id"] == 123456789
    assert user["username"] == "demo"


def test_validate_telegram_init_data_rejects_tampering():
    token = "123456:TEST_TOKEN"
    payload = _signed_init_data(token).replace("demo", "attacker")

    with pytest.raises(MiniAppAuthError):
        validate_telegram_init_data(payload, bot_token=token)
