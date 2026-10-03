import asyncio
import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from cachecontrol.cache import BaseCache

from app.config import get_settings

log = logging.getLogger(__name__)


class FirebaseVerificationUnavailable(RuntimeError):
    """Firebase signing certificates could not be checked right now."""


class CertificateCache(BaseCache):
    """Share HTTP certificate responses between web workers until their expiry."""

    def __init__(self, db_path: Path, *, clock=time.time):
        self.db_path = db_path
        self.clock = clock
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path, timeout=5) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS certificates "
                "(key TEXT PRIMARY KEY, value BLOB NOT NULL, expires_at REAL)"
            )

    def get(self, key: str) -> bytes | None:
        with sqlite3.connect(self.db_path, timeout=5) as db:
            row = db.execute(
                "SELECT value, expires_at FROM certificates WHERE key=?", (key,)
            ).fetchone()
            if not row:
                return None
            if row[1] is not None and row[1] <= self.clock():
                db.execute("DELETE FROM certificates WHERE key=?", (key,))
                return None
            return row[0]

    def set(self, key: str, value: bytes, expires: int | datetime | None = None) -> None:
        if isinstance(expires, datetime):
            expires_at = expires.timestamp()
        else:
            expires_at = self.clock() + expires if expires is not None else None
        with sqlite3.connect(self.db_path, timeout=5) as db:
            db.execute(
                "INSERT INTO certificates(key, value, expires_at) VALUES(?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, expires_at=excluded.expires_at",
                (key, value, expires_at),
            )

    def delete(self, key: str) -> None:
        with sqlite3.connect(self.db_path, timeout=5) as db:
            db.execute("DELETE FROM certificates WHERE key=?", (key,))


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
    from cachecontrol import CacheControl
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
    try:
        # The Admin SDK already uses Cache-Control for certificate responses,
        # but its default cache exists only in one web worker's memory. Share
        # still-valid public certificates across PythonAnywhere workers.
        request = auth._get_client(app)._token_verifier.request
        cache_path = Path(settings.MOBILE_DB_PATH).expanduser().resolve().parent / "firebase_cert_cache.sqlite3"
        CacheControl(request.session, cache=CertificateCache(cache_path))
        if proxy:
            # The Admin SDK exposes no public per-certificate proxy option.
            # Configure its dedicated requests session without changing the
            # process-wide proxy used by Yandex or other integrations.
            request.session.trust_env = False
            request.session.proxies.update({"http": proxy, "https": proxy})
    except Exception as exc:
        firebase_admin.delete_app(app)
        raise FirebaseVerificationUnavailable("Certificate transport setup failed") from exc
    return app


async def verify_phone_token(token: str):
    from firebase_admin import auth

    app = firebase_auth_app()
    for attempt in range(2):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    auth.verify_id_token,
                    token,
                    app=app,
                    check_revoked=False,
                ),
                timeout=get_settings().FIREBASE_HTTP_TIMEOUT_SECONDS + 4,
            )
        except (auth.CertificateFetchError, TimeoutError) as exc:
            log.warning("firebase_certificate_fetch_failed attempt=%s error_type=%s", attempt + 1, type(exc).__name__)
            if attempt == 1:
                raise FirebaseVerificationUnavailable("Firebase certificates unavailable") from exc
            await asyncio.sleep(0.5)


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
