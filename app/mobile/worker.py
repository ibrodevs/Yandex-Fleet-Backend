"""One Yandex poller, independent durable FCM and Telegram deliveries.

Run one process per shared database: python -m app.mobile.worker.
"""

import asyncio
import json
import logging
import time
from uuid import uuid4

from app.bot.factory import create_bot
from app.bot.presenters import order_text
from app.bot.storage import DriverLinkStore
from app.config import get_settings
from app.core.logging import log_event, setup_logging
from app.mobile.firebase import send_push
from app.mobile.storage import database, settings_for
from app.services.fleet.factory import close_fleet_provider, get_fleet_provider

log = logging.getLogger(__name__)
ACTIVE = {"assigned", "waiting", "in_progress"}
RETRY_WINDOW_SECONDS = 30 * 60
DELIVERY_TIMEOUT_SECONDS = 30


class MobileOrderWatcher:
    def __init__(self, provider=None, sender=send_push, *, telegram_sender=None, link_store=None):
        self.provider = provider or get_fleet_provider()
        self.sender = sender
        self.telegram_sender = telegram_sender
        self.link_store = link_store or DriverLinkStore(get_settings().TELEGRAM_BOT_DB_PATH)
        self._bot = None

    async def aclose(self):
        if self._bot is not None:
            await self._bot.session.close()
            self._bot = None

    async def _send_telegram(self, user_id, payload):
        if self.telegram_sender is not None:
            return await self.telegram_sender(user_id, payload)
        cfg = get_settings()
        if self._bot is None:
            self._bot = create_bot(cfg.TELEGRAM_BOT_TOKEN, http_proxy=cfg.TELEGRAM_HTTP_PROXY)
        order = {**payload, "id": payload["order_id"], "category": payload.get("tariff")}
        # Reuse the existing HTML-escaping bot presenter; no unsupported order actions.
        return await self._bot.send_message(
            chat_id=user_id,
            text="<b>Новый заказ · Яндекс</b>\n\n" + order_text(order),
            request_timeout=get_settings().TELEGRAM_BOT_REQUEST_TIMEOUT_SECONDS,
        )

    async def tick(self):
        tick_id = uuid4().hex
        started = time.monotonic()
        log_event(log, "order_watcher_poll_started", tick_id=tick_id)
        try:
            orders = await self.provider.list_orders()
        except Exception as exc:
            log_event(
                log,
                "order_watcher_poll_failed",
                level="warning",
                tick_id=tick_id,
                error_type=type(exc).__name__,
            )
            raise
        active = {
            (str(o["driver_id"]), str(o["id"])): o
            for o in orders
            if o.get("status") in ACTIVE and o.get("driver_id") and o.get("id")
        }
        detected = 0
        async with database() as db:
            for (driver_id, order_id), order in active.items():
                payload = {
                    key: order.get(key)
                    for key in (
                        "short_id",
                        "status",
                        "tariff",
                        "tariff_title",
                        "price",
                        "currency",
                        "payment_method",
                        "pickup",
                        "destination",
                        "distance_km",
                        "duration_minutes",
                    )
                }
                payload.update(type="new_order", order_id=order_id, driver_id=driver_id)
                cursor = await db.execute(
                    """INSERT OR IGNORE INTO mobile_order_events
                    (driver_id,order_id,event_type,order_status,payload) VALUES(?,?,?,?,?)""",
                    (driver_id, order_id, "NEW_ORDER", order["status"], json.dumps(payload)),
                )
                if cursor.rowcount:
                    detected += 1
                    log_event(
                        log,
                        "new_order_detected",
                        tick_id=tick_id,
                        event_id=cursor.lastrowid,
                        driver_id=driver_id,
                        order_id=order_id,
                        order_status=order["status"],
                    )
                # Retries use the latest status/details, without resetting event age or dedup.
                await db.execute(
                    """UPDATE mobile_order_events SET payload=?,order_status=?
                    WHERE driver_id=? AND order_id=? AND event_type='NEW_ORDER'""",
                    (json.dumps(payload), order["status"], driver_id, order_id),
                )
            rows = await (
                await db.execute(
                    """SELECT * FROM mobile_order_events WHERE event_type='NEW_ORDER'
                AND created_at >= datetime('now', ?)""",
                    (f"-{RETRY_WINDOW_SECONDS} seconds",),
                )
            ).fetchall()
        events = []
        for row in rows:
            event = dict(row)
            if (row["driver_id"], row["order_id"]) not in active:
                log_event(
                    log,
                    "order_delivery_skipped",
                    tick_id=tick_id,
                    event_id=row["id"],
                    driver_id=row["driver_id"],
                    order_id=row["order_id"],
                    reason="not_active",
                )
                continue
            events.append(event)
        # Failure (or a slow remote call) in one transport must not block the other transport.
        await asyncio.gather(
            self._channel("fcm", self._deliver_fcm, events, tick_id),
            self._channel("telegram", self._deliver_telegram, events, tick_id),
        )
        log_event(
            log,
            "order_watcher_poll_completed",
            tick_id=tick_id,
            orders_count=len(orders),
            active_count=len(active),
            detected_count=detected,
            eligible_count=len(events),
            duration_ms=round((time.monotonic() - started) * 1000),
        )

    async def _channel(self, channel, deliver, events, tick_id):
        try:
            await deliver(events, tick_id)
        except Exception as exc:
            # Includes storage/recipient lookup errors, not just network send errors.
            log_event(
                log,
                "order_delivery_channel_failed",
                level="warning",
                tick_id=tick_id,
                channel=channel,
                error_type=type(exc).__name__,
            )

    @staticmethod
    def _context(event, channel, recipient, tick_id):
        return dict(
            tick_id=tick_id,
            event_id=event["id"],
            driver_id=event["driver_id"],
            order_id=event["order_id"],
            order_status=event["order_status"],
            channel=channel,
            recipient_id=str(recipient),
        )

    async def _attempt(self, event, channel, recipient, tick_id, send):
        fields = self._context(event, channel, recipient, tick_id)
        key = (event["id"], channel, str(recipient))
        async with database() as db:
            fresh = await (
                await db.execute(
                    "SELECT 1 FROM mobile_order_events WHERE id=? AND created_at>=datetime('now',?)",
                    (event["id"], f"-{RETRY_WINDOW_SECONDS} seconds"),
                )
            ).fetchone()
            if not fresh:
                log_event(log, "order_delivery_skipped", **fields, reason="retry_window_expired")
                return False, None
            previous = await (
                await db.execute(
                    """SELECT * FROM mobile_delivery_attempts
                WHERE event_id=? AND channel=? AND recipient_id=?""",
                    key,
                )
            ).fetchone()
            if previous and previous["next_attempt_at"] > time.time():
                log_event(
                    log,
                    "order_delivery_skipped",
                    **fields,
                    reason="retry_after",
                    next_attempt_at=previous["next_attempt_at"],
                )
                return False, None
            attempt = (previous["attempts"] if previous else 0) + 1
            await db.execute(
                """INSERT INTO mobile_delivery_attempts
                (event_id,channel,recipient_id,attempts,last_attempt_at) VALUES(?,?,?,?,?)
                ON CONFLICT(event_id,channel,recipient_id) DO UPDATE SET
                attempts=excluded.attempts,last_attempt_at=excluded.last_attempt_at""",
                (*key, attempt, time.time()),
            )
        fields["attempt"] = attempt
        log_event(log, "order_delivery_attempt", **fields)
        started = time.monotonic()
        try:
            async with asyncio.timeout(DELIVERY_TIMEOUT_SECONDS):
                result = await send()
        except Exception as exc:
            # Never log exception text: SDK errors may contain tokens, URLs or personal data.
            retry_after = getattr(exc, "retry_after", 0)
            retry_after = max(0, retry_after) if isinstance(retry_after, (int, float)) else 0
            next_attempt = time.time() + retry_after
            async with database() as db:
                await db.execute(
                    """UPDATE mobile_delivery_attempts SET next_attempt_at=?,last_error_type=?
                    WHERE event_id=? AND channel=? AND recipient_id=?""",
                    (next_attempt, type(exc).__name__, *key),
                )
                if channel == "fcm" and type(exc).__name__ in {
                    "UnregisteredError",
                    "SenderIdMismatchError",
                }:
                    await db.execute("UPDATE mobile_devices SET enabled=0 WHERE id=?", (recipient,))
            log_event(
                log,
                "order_delivery_failed",
                level="warning",
                **fields,
                error_type=type(exc).__name__,
                next_attempt_at=next_attempt,
                duration_ms=round((time.monotonic() - started) * 1000),
            )
            return False, None
        # Persist success before considering this recipient complete. Telegram dedup is per event:
        # relinking an already notified driver must not notify the same order again.
        async with database() as db:
            if channel == "fcm":
                await db.execute(
                    "INSERT OR REPLACE INTO mobile_deliveries VALUES(?,?,CURRENT_TIMESTAMP)",
                    (event["id"], recipient),
                )
            else:
                await db.execute(
                    """INSERT OR IGNORE INTO mobile_telegram_deliveries
                    (event_id,telegram_user_id,message_id) VALUES(?,?,?)""",
                    (event["id"], recipient, getattr(result, "message_id", None)),
                )
            await db.execute(
                "UPDATE mobile_order_events SET notified_at=CURRENT_TIMESTAMP WHERE id=?",
                (event["id"],),
            )
            await db.execute(
                """UPDATE mobile_delivery_attempts SET last_error_type=NULL,next_attempt_at=0
                WHERE event_id=? AND channel=? AND recipient_id=?""",
                key,
            )
        log_event(
            log,
            "order_delivery_sent",
            **fields,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return True, result

    async def _deliver_fcm(self, events, tick_id):
        if not get_settings().MOBILE_ENABLED:
            log_event(log, "order_delivery_channel_disabled", channel="fcm", tick_id=tick_id)
            return
        for event in events:
            prefs = await settings_for(event["driver_id"])
            if not prefs.get("notifications", True):
                log_event(
                    log,
                    "order_delivery_skipped",
                    **self._context(event, "fcm", "", tick_id),
                    reason="notifications_disabled",
                )
                continue
            async with database() as db:
                devices = await (
                    await db.execute(
                        """SELECT d.*,x.sent_at FROM mobile_devices d
                    JOIN mobile_sessions s ON s.id=d.session_id AND s.driver_id=d.driver_id
                    AND s.revoked=0 AND s.expires_at>?
                    LEFT JOIN mobile_deliveries x ON x.event_id=? AND x.device_id=d.id
                    WHERE d.driver_id=? AND d.enabled=1""",
                        (int(time.time()), event["id"], event["driver_id"]),
                    )
                ).fetchall()
            if not devices:
                log_event(
                    log,
                    "order_delivery_skipped",
                    **self._context(event, "fcm", "", tick_id),
                    reason="no_devices",
                )
            for device in devices:
                if device["sent_at"]:
                    log_event(
                        log,
                        "order_delivery_deduplicated",
                        **self._context(event, "fcm", device["id"], tick_id),
                    )
                    continue
                payload = {**json.loads(event["payload"]), "sound": prefs.get("sound", True)}
                await self._attempt(
                    event,
                    "fcm",
                    device["id"],
                    tick_id,
                    lambda d=device, p=payload: self.sender(d["fcm_token"], p, d["platform"]),
                )

    async def _deliver_telegram(self, events, tick_id):
        if self.telegram_sender is None and not get_settings().TELEGRAM_BOT_TOKEN:
            log_event(
                log,
                "order_delivery_channel_disabled",
                channel="telegram",
                tick_id=tick_id,
                reason="missing_bot_token",
            )
            return
        await self.link_store.init()
        for event in events:
            async with database() as db:
                sent = await (
                    await db.execute(
                        "SELECT 1 FROM mobile_telegram_deliveries WHERE event_id=?",
                        (event["id"],),
                    )
                ).fetchone()
            if sent:
                log_event(
                    log,
                    "order_delivery_deduplicated",
                    **self._context(event, "telegram", "", tick_id),
                )
                continue
            link = await self.link_store.get_by_driver_id(event["driver_id"])
            if link is None:
                log_event(
                    log,
                    "order_delivery_skipped",
                    **self._context(event, "telegram", "", tick_id),
                    reason="no_driver_link",
                )
                continue
            await self._attempt(
                event,
                "telegram",
                link.telegram_user_id,
                tick_id,
                lambda user=link.telegram_user_id, p=json.loads(event["payload"]): (
                    self._send_telegram(user, p)
                ),
            )


async def main():
    cfg = get_settings()
    setup_logging(cfg.LOG_LEVEL)
    if not cfg.MOBILE_ORDER_WATCHER_ENABLED:
        log_event(log, "order_watcher_disabled")
        return
    if cfg.YANDEX_MOCK_MODE:
        raise RuntimeError("Order worker requires YANDEX_MOCK_MODE=false")
    import fcntl
    from pathlib import Path

    Path(cfg.MOBILE_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(cfg.MOBILE_DB_PATH + ".worker.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        watcher = MobileOrderWatcher()
        log_event(
            log,
            "order_watcher_started",
            poll_interval_seconds=cfg.MOBILE_ORDER_POLL_INTERVAL_SECONDS,
            retry_window_seconds=RETRY_WINDOW_SECONDS,
            fcm_enabled=cfg.MOBILE_ENABLED,
            telegram_configured=bool(cfg.TELEGRAM_BOT_TOKEN),
        )
        try:
            while True:
                try:
                    await watcher.tick()
                except Exception as exc:
                    log_event(
                        log,
                        "order_watcher_tick_failed",
                        level="warning",
                        error_type=type(exc).__name__,
                    )
                await asyncio.sleep(cfg.MOBILE_ORDER_POLL_INTERVAL_SECONDS)
        finally:
            try:
                await watcher.aclose()
            finally:
                await close_fleet_provider()
                log_event(log, "order_watcher_stopped")


if __name__ == "__main__":
    asyncio.run(main())
