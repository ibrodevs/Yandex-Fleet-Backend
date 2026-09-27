"""Run exactly one process: python -m app.mobile.worker."""

import asyncio
import json
import logging
import time

from app.config import get_settings
from app.mobile.firebase import send_push
from app.mobile.storage import database, settings_for
from app.services.fleet.factory import close_fleet_provider, get_fleet_provider

log = logging.getLogger(__name__)
ACTIVE = {"assigned", "waiting", "in_progress"}


class MobileOrderWatcher:
    def __init__(self, provider=None, sender=send_push):
        self.provider = provider or get_fleet_provider()
        self.sender = sender

    async def tick(self):
        orders = await self.provider.list_orders()
        async with database() as db:
            for order in orders:
                if (
                    order.get("status") not in ACTIVE
                    or not order.get("driver_id")
                    or not order.get("id")
                ):
                    continue
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
                payload.update(
                    type="new_order", order_id=str(order["id"]), driver_id=str(order["driver_id"])
                )
                cursor = await db.execute(
                    """INSERT OR IGNORE INTO mobile_order_events
                    (driver_id,order_id,event_type,order_status,payload) VALUES(?,?,?,?,?)""",
                    (
                        str(order["driver_id"]),
                        str(order["id"]),
                        "NEW_ORDER",
                        order["status"],
                        json.dumps(payload),
                    ),
                )
                if cursor.rowcount:
                    log.info("new_order_detected")
        # Durable per-device deliveries: failures retry, successful devices are not resent.
        # FCM has no exactly-once guarantee; Android also deduplicates event/order IDs.
        async with database() as db:
            pending = await (
                await db.execute(
                    """SELECT e.id event_id,e.payload,d.* FROM mobile_order_events e
                JOIN mobile_devices d ON d.driver_id=e.driver_id AND d.enabled=1
                JOIN mobile_sessions s ON s.id=d.session_id AND s.revoked=0 AND s.expires_at>?
                LEFT JOIN mobile_deliveries x ON x.event_id=e.id AND x.device_id=d.id
                WHERE x.sent_at IS NULL AND e.created_at >= datetime('now','-2 minutes')""",
                    (int(time.time()),),
                )
            ).fetchall()
        active_ids = {
            (str(o.get("driver_id")), str(o.get("id"))) for o in orders if o.get("status") in ACTIVE
        }
        for delivery in pending:
            payload = json.loads(delivery["payload"])
            if (delivery["driver_id"], payload["order_id"]) not in active_ids:
                continue
            prefs = await settings_for(delivery["driver_id"])
            if not prefs.get("notifications", True):
                continue
            payload["sound"] = prefs.get("sound", True)
            try:
                await self.sender(delivery["fcm_token"], payload, delivery["platform"])
            except Exception as exc:
                log.warning("push_failed type=%s", type(exc).__name__)
                if type(exc).__name__ in {"UnregisteredError", "SenderIdMismatchError"}:
                    async with database() as db:
                        await db.execute(
                            "UPDATE mobile_devices SET enabled=0 WHERE id=?", (delivery["id"],)
                        )
                continue
            async with database() as db:
                await db.execute(
                    "INSERT OR REPLACE INTO mobile_deliveries VALUES(?,?,CURRENT_TIMESTAMP)",
                    (delivery["event_id"], delivery["id"]),
                )
                await db.execute(
                    "UPDATE mobile_order_events SET notified_at=CURRENT_TIMESTAMP WHERE id=?",
                    (delivery["event_id"],),
                )
            log.info("push_sent")


async def main():
    cfg = get_settings()
    if not cfg.MOBILE_ENABLED or not cfg.MOBILE_ORDER_WATCHER_ENABLED:
        return
    if cfg.YANDEX_MOCK_MODE:
        raise RuntimeError("Mobile worker requires YANDEX_MOCK_MODE=false")
    # Local advisory lock prevents duplicate worker processes on PythonAnywhere.
    import fcntl
    from pathlib import Path

    Path(cfg.MOBILE_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(cfg.MOBILE_DB_PATH + ".worker.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        watcher = MobileOrderWatcher()
        try:
            while True:
                try:
                    await watcher.tick()
                except Exception as exc:
                    log.warning("mobile_watcher_failed type=%s", type(exc).__name__)
                await asyncio.sleep(cfg.MOBILE_ORDER_POLL_INTERVAL_SECONDS)
        finally:
            await close_fleet_provider()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
