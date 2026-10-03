import asyncio
import json
from datetime import timedelta
from functools import lru_cache
from urllib.parse import urlparse

from app.config import get_settings


class FirebaseVerificationUnavailable(RuntimeError):
    """Firebase signing certificates could not be checked right now."""


def _certificate_proxy(settings) -> str | None:
    if settings.FIREBASE_CERT_PROXY:
        return settings.FIREBASE_CERT_PROXY
    # PythonAnywhere's outbound HTTP proxy is required on restricted accounts.
    # Route only Firebase's certificate fetch through it; Yandex keeps its own
    # network configuration.
    urls = (settings.TELEGRAM_WEBHOOK_BASE_URL, settings.TELEGRAM_MINI_APP_URL)
    if any(
        (urlparse(url).hostname or "").endswith(".pythonanywhere.com")
        for url in urls
    ):
        return "http://proxy.server:3128"
    return None


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


@lru_cache
def firebase_auth_app():
    import firebase_admin
    from firebase_admin import auth, credentials

    settings = get_settings()
    if not settings.FIREBASE_PROJECT_ID or not settings.FIREBASE_CREDENTIALS_FILE:
        raise RuntimeError("Firebase is not configured")
    app = firebase_admin.initialize_app(
        credentials.Certificate(settings.FIREBASE_CREDENTIALS_FILE),
        {
            "projectId": settings.FIREBASE_PROJECT_ID,
            "httpTimeout": settings.FIREBASE_HTTP_TIMEOUT_SECONDS,
        },
        name="mobile-auth",
    )
    proxy = _certificate_proxy(settings)
    if proxy:
        try:
            # The Admin SDK exposes no public per-certificate proxy option.
            # Configure its dedicated requests session without changing the
            # process-wide proxy used by Yandex or other integrations.
            request = auth._get_client(app)._token_verifier.request
            request.session.trust_env = False
            request.session.proxies.update({"http": proxy, "https": proxy})
        except Exception as exc:
            firebase_admin.delete_app(app)
            raise FirebaseVerificationUnavailable("Certificate proxy setup failed") from exc
    return app


async def verify_phone_token(token: str):
    from firebase_admin import auth

    app = firebase_auth_app()
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                auth.verify_id_token,
                token,
                app=app,
                check_revoked=False,
            ),
            timeout=get_settings().FIREBASE_HTTP_TIMEOUT_SECONDS + 2,
        )
    except (auth.CertificateFetchError, TimeoutError) as exc:
        raise FirebaseVerificationUnavailable("Firebase certificates unavailable") from exc


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
