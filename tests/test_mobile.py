import time
from unittest.mock import AsyncMock

import httpx
import jwt
import pytest

from app.config import Settings, get_settings
from app.core.exceptions import YandexRateLimitError
from app.main import app
from app.mobile import router as mobile
from app.mobile.storage import database
from app.mobile.worker import MobileOrderWatcher
from app.services.fleet.yandex import YandexFleetProvider
from app.services.yandex.cache import SharedYandexCache
from tests.test_yandex_mappers import order_fixture


@pytest.fixture
async def client(tmp_path, monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "TELEGRAM_BOT_TOKEN", None)
    monkeypatch.setattr(cfg, "MOBILE_DB_PATH", str(tmp_path / "mobile.db"))
    monkeypatch.setattr(cfg, "YANDEX_MOCK_MODE", False)
    monkeypatch.setattr(cfg, "SECRET_KEY", "mobile-test-secret-" * 3)
    monkeypatch.setattr(cfg, "FIREBASE_PROJECT_ID", "test")
    monkeypatch.setattr(cfg, "FIREBASE_CREDENTIALS_FILE", "unused")
    monkeypatch.setattr(cfg, "APP_ENV", "development")
    provider = AsyncMock()
    provider.get_driver_by_phone.return_value = {"id": "a"}
    provider.get_driver.return_value = {"id": "a", "vehicle": {"plate": "A"}}
    provider.get_order.return_value = {"id": "foreign", "driver_id": "b"}
    provider.list_orders.return_value = [
        {"id": "1", "driver_id": "a", "status": "assigned"},
        {"id": "2", "driver_id": "b"},
    ]
    monkeypatch.setattr(mobile, "get_fleet_provider", lambda: provider)
    monkeypatch.setattr(
        mobile,
        "verify_phone_token",
        AsyncMock(
            return_value={
                "phone_number": "+996555111222",
                "firebase": {"sign_in_provider": "phone"},
            }
        ),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c, provider


async def login(c):
    result = await c.post("/api/v1/mobile/auth/firebase", json={"id_token": "firebase-token"})
    assert result.status_code == 200
    c.headers["Authorization"] = "Bearer " + result.json()["access_token"]
    return result.json()["access_token"]


async def test_mobile_auth(client, monkeypatch):
    c, p = client
    assert (await c.get("/api/v1/mobile/me")).status_code == 401
    token = await login(c)
    claims = jwt.decode(
        token, get_settings().SECRET_KEY, algorithms=["HS256"], audience="fleet-mobile"
    )
    assert claims["driver_id"] == "a"
    p.get_driver_by_phone.assert_awaited_once_with("+996555111222")
    assert (await c.get("/api/v1/mobile/me")).json()["id"] == "a"
    await c.post("/api/v1/mobile/auth/logout")
    assert (await c.get("/api/v1/mobile/me")).status_code == 401
    monkeypatch.setattr(mobile, "verify_phone_token", AsyncMock(side_effect=ValueError()))
    assert (
        await c.post("/api/v1/mobile/auth/firebase", json={"id_token": "invalid-token"})
    ).status_code == 401


async def test_driver_cannot_read_foreign_order(client):
    c, _ = client
    await login(c)
    assert (await c.get("/api/v1/mobile/orders/foreign")).status_code == 404
    orders = (await c.get("/api/v1/mobile/orders?driver_id=b")).json()
    assert len(orders) == 1
    assert orders[0]["driver_id"] == "a"
    assert orders[0]["can_accept"] is False


async def test_device_registration(client):
    c, _ = client
    await login(c)
    for token in ["first-fcm-token", "second-fcm-token"]:
        assert (
            await c.post(
                "/api/v1/mobile/devices",
                json={"fcm_token": token, "platform": "android", "device_id": "installation-1"},
            )
        ).status_code == 200
    async with database() as db:
        rows = await (await db.execute("SELECT * FROM mobile_devices")).fetchall()
    assert len(rows) == 1 and rows[0]["fcm_token"] == "second-fcm-token"
    await c.post("/api/v1/mobile/auth/logout")
    async with database() as db:
        row = await (await db.execute("SELECT enabled FROM mobile_devices")).fetchone()
    assert row[0] == 0


async def test_push_deduplication_and_retry(client):
    c, p = client
    await login(c)
    await c.post(
        "/api/v1/mobile/devices",
        json={"fcm_token": "first-fcm-token", "platform": "android", "device_id": "installation-1"},
    )
    sender = AsyncMock(side_effect=[RuntimeError(), "sent"])
    watcher = MobileOrderWatcher(p, sender)
    for _ in range(4):
        await watcher.tick()
    assert sender.await_count == 2
    async with database() as db:
        assert (await (await db.execute("SELECT COUNT(*) FROM mobile_order_events")).fetchone())[
            0
        ] == 1
        assert (await (await db.execute("SELECT COUNT(*) FROM mobile_deliveries")).fetchone())[
            0
        ] == 1


async def test_settings_validation_and_debug_protection(client, monkeypatch):
    c, _ = client
    await login(c)
    assert (await c.put("/api/v1/mobile/settings", json={"transparency": 90})).status_code == 422
    assert (await c.put("/api/v1/mobile/settings", json={"display_seconds": 7})).status_code == 422
    assert (await c.put("/api/v1/mobile/settings", json={"sound": False})).json()["sound"] is False
    assert (await c.get("/api/v1/mobile/settings")).json()["sound"] is False
    monkeypatch.setattr(get_settings(), "APP_ENV", "production")
    assert (
        await c.post("/api/v1/mobile/debug/test-notification", json={"device_id": "some-device"})
    ).status_code == 404


async def test_expired_session(client):
    c, _ = client
    await login(c)
    async with database() as db:
        await db.execute("UPDATE mobile_sessions SET expires_at=?", (int(time.time()) - 1,))
    assert (await c.get("/api/v1/mobile/orders")).status_code == 401


async def test_mobile_orders_serves_bounded_stale_snapshot_on_yandex_429(
    client, tmp_path, monkeypatch
):
    c, _ = client
    await login(c)
    now = [100.0]

    class RateLimitedAfterFirstCall:
        def __init__(self):
            self.calls = 0

        async def list_orders(self, **_kwargs):
            self.calls += 1
            if self.calls > 1:
                raise YandexRateLimitError()
            order = order_fixture()
            order["driver_profile"] = {"id": "a", "name": "Тест"}
            return [order]

        async def aclose(self):
            return None

    cfg = Settings(
        YANDEX_CLIENT_ID="test-client",
        YANDEX_API_KEY="test-key",
        YANDEX_PARK_ID="test-park",
        YANDEX_MOCK_MODE=False,
        YANDEX_CACHE_DB_PATH=str(tmp_path / "yandex-cache.sqlite3"),
        YANDEX_ORDERS_CACHE_TTL_SECONDS=10,
        YANDEX_CACHE_STALE_SECONDS=60,
    )
    yandex_client = RateLimitedAfterFirstCall()
    cache = SharedYandexCache(cfg.YANDEX_CACHE_DB_PATH, clock=lambda: now[0])
    provider = YandexFleetProvider(yandex_client, settings=cfg, cache=cache)
    assert len(await provider.list_orders()) == 1
    now[0] += 11
    monkeypatch.setattr(mobile, "get_fleet_provider", lambda: provider)

    response = await c.get("/api/v1/mobile/orders")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["order-1"]
    assert yandex_client.calls == 2


async def test_completed_order_is_not_retried(client):
    c, p = client
    await login(c)
    await c.post(
        "/api/v1/mobile/devices",
        json={"fcm_token": "first-fcm-token", "platform": "android", "device_id": "installation-1"},
    )
    sender = AsyncMock(side_effect=RuntimeError())
    watcher = MobileOrderWatcher(p, sender)
    await watcher.tick()
    p.list_orders.return_value = [{"id": "1", "driver_id": "a", "status": "completed"}]
    await watcher.tick()
    assert sender.await_count == 1


async def test_push_respects_settings_and_recipient(client):
    c, p = client
    await login(c)
    await c.post(
        "/api/v1/mobile/devices",
        json={"fcm_token": "first-fcm-token", "platform": "android", "device_id": "installation-1"},
    )
    await c.put("/api/v1/mobile/settings", json={"notifications": False})
    sender = AsyncMock()
    watcher = MobileOrderWatcher(p, sender)
    await watcher.tick()
    sender.assert_not_awaited()
    await c.put("/api/v1/mobile/settings", json={"sound": False})
    await watcher.tick()
    payload = sender.call_args.args[1]
    assert payload["driver_id"] == "a"
    assert payload["sound"] is False
    assert payload["price"] is None
