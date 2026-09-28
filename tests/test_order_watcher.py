import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.storage import DriverLinkStore
from app.config import get_settings
from app.core.logging import StructuredJsonFormatter
from app.mobile.storage import database
from app.mobile.worker import MobileOrderWatcher


@pytest.fixture
async def delivery(tmp_path, monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "MOBILE_DB_PATH", str(tmp_path / "mobile.sqlite3"))
    monkeypatch.setattr(cfg, "TELEGRAM_BOT_DB_PATH", str(tmp_path / "telegram.sqlite3"))
    monkeypatch.setattr(cfg, "TELEGRAM_BOT_TOKEN", None)
    monkeypatch.setattr(cfg, "MOBILE_ENABLED", True)
    store = DriverLinkStore(cfg.TELEGRAM_BOT_DB_PATH)
    await store.init()
    await store.link(
        telegram_user_id=123,
        driver_id="driver",
        phone=None,
        username=None,
        first_name=None,
        last_name=None,
    )
    async with database() as db:
        await db.execute(
            "INSERT INTO mobile_sessions VALUES('session','driver','private-phone',?,0)",
            (int(time.time()) + 3600,),
        )
        await db.execute("""INSERT INTO mobile_devices
            (id,driver_id,session_id,fcm_token,platform,device_id)
            VALUES('device','driver','session','private-fcm-token','android','installation')""")
    provider = AsyncMock()
    provider.list_orders.return_value = [
        {"id": "order", "driver_id": "driver", "status": "assigned", "pickup": "private address"}
    ]
    fcm = AsyncMock(return_value="message")
    telegram = AsyncMock(return_value=SimpleNamespace(message_id=42))
    watcher = MobileOrderWatcher(provider, fcm, telegram_sender=telegram, link_store=store)
    return SimpleNamespace(
        provider=provider, fcm=fcm, telegram=telegram, watcher=watcher, store=store
    )


async def test_both_channels_single_poll_and_durable_restart_dedup(delivery):
    d = delivery
    await d.watcher.tick()
    d.provider.list_orders.assert_awaited_once_with()
    d.fcm.assert_awaited_once()
    d.telegram.assert_awaited_once()
    assert d.telegram.call_args.args[0] == 123
    async with database() as db:
        row = await (await db.execute("SELECT * FROM mobile_telegram_deliveries")).fetchone()
        assert row["message_id"] == 42
        assert row["telegram_user_id"] == 123
    restarted = MobileOrderWatcher(
        d.provider, d.fcm, telegram_sender=d.telegram, link_store=d.store
    )
    await restarted.tick()
    assert d.fcm.await_count == 1
    assert d.telegram.await_count == 1


@pytest.mark.parametrize("failed", ["fcm", "telegram"])
async def test_channels_retry_independently(delivery, failed):
    d = delivery
    sender = getattr(d, failed)
    sender.side_effect = [RuntimeError("private-token-in-error"), SimpleNamespace(message_id=9)]
    await d.watcher.tick()
    await MobileOrderWatcher(
        d.provider, d.fcm, telegram_sender=d.telegram, link_store=d.store
    ).tick()
    await d.watcher.tick()
    assert sender.await_count == 2
    assert getattr(d, "telegram" if failed == "fcm" else "fcm").await_count == 1
    async with database() as db:
        row = await (
            await db.execute(
                "SELECT attempts,last_error_type FROM mobile_delivery_attempts WHERE channel=?",
                (failed,),
            )
        ).fetchone()
        assert tuple(row) == (2, None)


@pytest.mark.parametrize("minutes,eligible", [(3, True), (29, True), (31, False)])
async def test_retry_window_is_30_minutes(delivery, minutes, eligible):
    d = delivery
    d.fcm.side_effect = RuntimeError()
    d.telegram.side_effect = RuntimeError()
    await d.watcher.tick()
    async with database() as db:
        await db.execute(
            "UPDATE mobile_order_events SET created_at=datetime('now',?)", (f"-{minutes} minutes",)
        )
    d.fcm.side_effect = None
    d.telegram.side_effect = None
    await d.watcher.tick()
    assert d.fcm.await_count == 1 + eligible
    assert d.telegram.await_count == 1 + eligible


@pytest.mark.parametrize("status", ["completed", "cancelled", "unknown", None])
async def test_inactive_or_missing_order_stops_both_retries(delivery, status):
    d = delivery
    d.fcm.side_effect = RuntimeError()
    d.telegram.side_effect = RuntimeError()
    await d.watcher.tick()
    d.provider.list_orders.return_value = (
        [] if status is None else [{"id": "order", "driver_id": "driver", "status": status}]
    )
    await d.watcher.tick()
    assert d.fcm.await_count == d.telegram.await_count == 1


async def test_telegram_only_no_mobile_devices_or_notifications(delivery, monkeypatch):
    d = delivery
    monkeypatch.setattr(get_settings(), "MOBILE_ENABLED", False)
    async with database() as db:
        await db.execute("DELETE FROM mobile_devices")
        await db.execute(
            "INSERT INTO mobile_settings VALUES('driver',?)",
            (json.dumps({"notifications": False}),),
        )
    await d.watcher.tick()
    d.telegram.assert_awaited_once()
    d.fcm.assert_not_awaited()


async def test_mobile_opt_out_does_not_disable_telegram(delivery):
    d = delivery
    async with database() as db:
        await db.execute(
            "INSERT INTO mobile_settings VALUES('driver',?)",
            (json.dumps({"notifications": False}),),
        )
    await d.watcher.tick()
    d.telegram.assert_awaited_once()
    d.fcm.assert_not_awaited()


async def test_link_missing_then_created_while_order_active(delivery):
    d = delivery
    await d.store.unlink(123)
    await d.watcher.tick()
    d.telegram.assert_not_awaited()
    d.fcm.assert_awaited_once()
    await d.store.link(
        telegram_user_id=456,
        driver_id="driver",
        phone=None,
        username=None,
        first_name=None,
        last_name=None,
    )
    await d.watcher.tick()
    assert d.telegram.call_args.args[0] == 456
    d.fcm.assert_awaited_once()


async def test_retry_resolves_current_binding_and_success_survives_relink(delivery):
    d = delivery
    d.telegram.side_effect = [RuntimeError(), SimpleNamespace(message_id=2)]
    await d.watcher.tick()
    await d.store.link(
        telegram_user_id=456,
        driver_id="driver",
        phone=None,
        username=None,
        first_name=None,
        last_name=None,
    )
    await d.watcher.tick()
    assert [c.args[0] for c in d.telegram.call_args_list] == [123, 456]
    await d.store.link(
        telegram_user_id=789,
        driver_id="driver",
        phone=None,
        username=None,
        first_name=None,
        last_name=None,
    )
    await d.watcher.tick()
    assert d.telegram.await_count == 2


async def test_telegram_lookup_failure_does_not_block_fcm(delivery):
    d = delivery
    d.store.get_by_driver_id = AsyncMock(side_effect=RuntimeError())
    await d.watcher.tick()
    d.fcm.assert_awaited_once()
    d.telegram.assert_not_awaited()


async def test_slow_fcm_does_not_delay_telegram(delivery):
    d = delivery
    release = asyncio.Event()
    delivered = asyncio.Event()

    async def slow(*args):
        await release.wait()

    async def telegram(*args):
        delivered.set()
        return SimpleNamespace(message_id=1)

    d.watcher.sender = slow
    d.watcher.telegram_sender = telegram
    task = asyncio.create_task(d.watcher.tick())
    try:
        await asyncio.wait_for(delivered.wait(), timeout=2)
    finally:
        release.set()
        await task


async def test_rate_limit_retry_after_is_durable_and_channel_specific(delivery):
    d = delivery

    class RateLimit(Exception):
        retry_after = 60

    d.telegram.side_effect = RateLimit()
    await d.watcher.tick()
    await MobileOrderWatcher(
        d.provider, d.fcm, telegram_sender=d.telegram, link_store=d.store
    ).tick()
    assert d.telegram.await_count == 1
    d.fcm.assert_awaited_once()
    async with database() as db:
        await db.execute(
            "UPDATE mobile_delivery_attempts SET next_attempt_at=0 WHERE channel='telegram'"
        )
    d.telegram.side_effect = None
    await d.watcher.tick()
    assert d.telegram.await_count == 2


async def test_updated_status_and_payload_on_retry(delivery):
    d = delivery
    d.telegram.side_effect = [RuntimeError(), SimpleNamespace(message_id=4)]
    await d.watcher.tick()
    d.provider.list_orders.return_value[0].update(status="in_progress", price=100)
    await d.watcher.tick()
    assert d.telegram.call_args.args[1]["status"] == "in_progress"
    assert d.telegram.call_args.args[1]["price"] == 100


async def test_structured_logs_have_context_without_sensitive_values(delivery, caplog):
    d = delivery
    d.telegram.side_effect = RuntimeError("private-token-in-error")
    with caplog.at_level("INFO", logger="app.mobile.worker"):
        await d.watcher.tick()
    records = [
        json.loads(StructuredJsonFormatter().format(r))
        for r in caplog.records
        if r.name == "app.mobile.worker"
    ]
    failure = next(r for r in records if r["event"] == "order_delivery_failed")
    assert failure["channel"] == "telegram"
    assert failure["driver_id"] == "driver" and failure["order_id"] == "order"
    assert failure["recipient_id"] == "123" and failure["attempt"] == 1
    assert failure["error_type"] == "RuntimeError" and failure["tick_id"]
    serialized = json.dumps(records)
    for private in [
        "private-token-in-error",
        "private-fcm-token",
        "private-phone",
        "private address",
    ]:
        assert private not in serialized


async def test_telegram_adapter_escapes_html_and_closes_session(delivery, monkeypatch):
    from app.mobile import worker

    d = delivery
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=99)),
        session=SimpleNamespace(close=AsyncMock()),
    )
    monkeypatch.setattr(worker, "create_bot", lambda *args, **kwargs: bot)
    monkeypatch.setattr(get_settings(), "TELEGRAM_BOT_TOKEN", "test-token")
    d.watcher.telegram_sender = None
    d.provider.list_orders.return_value[0]["pickup"] = "<b>unsafe & address</b>"
    await d.watcher.tick()
    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == 123
    assert "&lt;b&gt;unsafe &amp; address&lt;/b&gt;" in kwargs["text"]
    await d.watcher.aclose()
    bot.session.close.assert_awaited_once()


async def test_fcm_retry_per_device_not_per_event(delivery):
    d = delivery
    async with database() as db:
        await db.execute("""INSERT INTO mobile_devices
            (id,driver_id,session_id,fcm_token,platform,device_id)
            VALUES('second','driver','session','other-token','android','other-installation')""")
    calls = []

    async def send(token, *args):
        calls.append(token)
        if token == "other-token" and calls.count(token) == 1:
            raise RuntimeError()

    d.watcher.sender = send
    await d.watcher.tick()
    await d.watcher.tick()
    assert calls.count("private-fcm-token") == 1
    assert calls.count("other-token") == 2
    d.telegram.assert_awaited_once()


async def test_no_bot_token_does_not_block_fcm(delivery):
    d = delivery
    d.watcher.telegram_sender = None
    await d.watcher.tick()
    d.fcm.assert_awaited_once()
    d.telegram.assert_not_awaited()


async def test_poll_failure_never_delivers_from_stale_snapshot(delivery):
    d = delivery
    d.fcm.side_effect = RuntimeError()
    d.telegram.side_effect = RuntimeError()
    await d.watcher.tick()
    d.provider.list_orders.side_effect = RuntimeError()
    with pytest.raises(RuntimeError):
        await d.watcher.tick()
    assert d.fcm.await_count == d.telegram.await_count == 1


async def test_expired_while_queued_is_not_sent(delivery):
    d = delivery
    d.telegram.side_effect = RuntimeError()
    await d.watcher.tick()
    async with database() as db:
        event = dict(await (await db.execute("SELECT * FROM mobile_order_events")).fetchone())
        await db.execute("UPDATE mobile_order_events SET created_at=datetime('now','-31 minutes')")
    sender = AsyncMock()
    await d.watcher._attempt(event, "telegram", 123, "tick", sender)
    sender.assert_not_awaited()


async def test_invalid_fcm_device_disabled_without_affecting_telegram(delivery):
    d = delivery

    class UnregisteredError(Exception):
        pass

    d.fcm.side_effect = UnregisteredError()
    await d.watcher.tick()
    await d.watcher.tick()
    d.fcm.assert_awaited_once()
    d.telegram.assert_awaited_once()
    async with database() as db:
        assert (await (await db.execute("SELECT enabled FROM mobile_devices")).fetchone())[0] == 0
