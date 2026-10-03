from types import SimpleNamespace

import firebase_admin
import pytest
from firebase_admin import auth, credentials

from app.config import Settings
from app.mobile import firebase as mobile_firebase


def test_pythonanywhere_certificate_proxy_is_scoped_to_firebase():
    cfg = Settings(
        TELEGRAM_WEBHOOK_BASE_URL="https://yandexfeetbackend21.pythonanywhere.com",
        FIREBASE_CERT_PROXY="",
    )
    assert mobile_firebase._certificate_proxy(cfg) == "http://proxy.server:3128"
    cfg.FIREBASE_CERT_PROXY = "http://other-proxy:3128"
    assert mobile_firebase._certificate_proxy(cfg) == "http://other-proxy:3128"


def test_auth_app_sets_short_timeout_and_proxy_without_changing_push_app(monkeypatch):
    cfg = Settings(
        FIREBASE_PROJECT_ID="test-project",
        FIREBASE_CREDENTIALS_FILE="unused.json",
        FIREBASE_HTTP_TIMEOUT_SECONDS=8,
        TELEGRAM_WEBHOOK_BASE_URL="https://yandexfeetbackend21.pythonanywhere.com",
    )
    session = SimpleNamespace(trust_env=True, proxies={})
    client = SimpleNamespace(_token_verifier=SimpleNamespace(
        request=SimpleNamespace(session=session)
    ))
    calls = []
    fake_app = object()
    monkeypatch.setattr(mobile_firebase, "get_settings", lambda: cfg)
    monkeypatch.setattr(credentials, "Certificate", lambda path: path)
    monkeypatch.setattr(firebase_admin, "initialize_app", lambda *args, **kwargs: (
        calls.append((args, kwargs)) or fake_app
    ))
    monkeypatch.setattr(auth, "_get_client", lambda app: client)
    mobile_firebase.firebase_app.cache_clear()
    mobile_firebase.firebase_auth_app.cache_clear()
    try:
        assert mobile_firebase.firebase_app() is fake_app
        assert mobile_firebase.firebase_auth_app() is fake_app
    finally:
        mobile_firebase.firebase_app.cache_clear()
        mobile_firebase.firebase_auth_app.cache_clear()
    assert calls[0][0][1] == {"projectId": "test-project"}
    assert calls[0][1]["name"] == "mobile"
    assert calls[1][0][1] == {"projectId": "test-project", "httpTimeout": 8}
    assert calls[1][1]["name"] == "mobile-auth"
    assert session.trust_env is False
    assert session.proxies == {
        "http": "http://proxy.server:3128",
        "https": "http://proxy.server:3128",
    }


@pytest.mark.asyncio
async def test_certificate_fetch_failure_is_unavailable(monkeypatch):
    monkeypatch.setattr(mobile_firebase, "firebase_auth_app", lambda: object())
    monkeypatch.setattr(
        auth,
        "verify_id_token",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            auth.CertificateFetchError("certificates unavailable", cause=None)
        ),
    )
    with pytest.raises(mobile_firebase.FirebaseVerificationUnavailable):
        await mobile_firebase.verify_phone_token("fake-token")
