import asyncio
import json
from datetime import timedelta
from functools import lru_cache

from app.config import get_settings


@lru_cache
def firebase_app():
    import firebase_admin
    from firebase_admin import credentials

    settings = get_settings()
    if not settings.FIREBASE_PROJECT_ID or not settings.FIREBASE_CREDENTIALS_FILE:
        raise RuntimeError("Firebase is not configured")
    return firebase_admin.initialize_app(
        credentials.Certificate(settings.FIREBASE_CREDENTIALS_FILE),
        {"projectId": settings.FIREBASE_PROJECT_ID},
        name="mobile",
    )


async def verify_phone_token(token: str):
    from firebase_admin import auth

    return await asyncio.to_thread(
        auth.verify_id_token,
        token,
        app=firebase_app(),
        check_revoked=True,
    )


async def send_push(token: str, payload: dict, platform: str):
    from firebase_admin import messaging

    data = {
        "payload": json.dumps(payload, ensure_ascii=False),
        "type": payload["type"],
        "order_id": payload["order_id"],
    }
    message = messaging.Message(
        token=token,
        data=data,
        android=messaging.AndroidConfig(priority="high", ttl=timedelta(minutes=2)),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    alert=messaging.ApsAlert(
                        title="Новый заказ", body=payload.get("tariff_title") or "Яндекс"
                    ),
                    sound="default" if payload.get("sound", True) else None,
                )
            )
        ),
    )
    return await asyncio.to_thread(messaging.send, message, app=firebase_app())
