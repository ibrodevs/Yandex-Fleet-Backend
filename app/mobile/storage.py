import json
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS mobile_sessions (
 id TEXT PRIMARY KEY, driver_id TEXT NOT NULL, phone TEXT NOT NULL,
 expires_at INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS mobile_devices (
 id TEXT PRIMARY KEY, driver_id TEXT NOT NULL, session_id TEXT NOT NULL,
 fcm_token TEXT NOT NULL UNIQUE, platform TEXT NOT NULL,
 device_id TEXT NOT NULL UNIQUE, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT DEFAULT CURRENT_TIMESTAMP, last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
 enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS mobile_settings (driver_id TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mobile_order_events (
 id INTEGER PRIMARY KEY, driver_id TEXT NOT NULL, order_id TEXT NOT NULL,
 event_type TEXT NOT NULL, order_status TEXT NOT NULL, payload TEXT NOT NULL,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP, notified_at TEXT,
 UNIQUE(driver_id, order_id, event_type));
CREATE TABLE IF NOT EXISTS mobile_deliveries (
 event_id INTEGER NOT NULL, device_id TEXT NOT NULL, sent_at TEXT,
 PRIMARY KEY(event_id, device_id));
CREATE TABLE IF NOT EXISTS mobile_telegram_deliveries (
 event_id INTEGER PRIMARY KEY, telegram_user_id INTEGER NOT NULL,
 message_id INTEGER, sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS mobile_delivery_attempts (
 event_id INTEGER NOT NULL, channel TEXT NOT NULL, recipient_id TEXT NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0, last_attempt_at REAL,
 next_attempt_at REAL NOT NULL DEFAULT 0, last_error_type TEXT,
 PRIMARY KEY(event_id, channel, recipient_id));
"""


@asynccontextmanager
async def database():
    path = get_settings().MOBILE_DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path, timeout=30) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript(SCHEMA)
        await db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def settings_for(driver_id):
    async with database() as db:
        row = await (
            await db.execute("SELECT value FROM mobile_settings WHERE driver_id=?", (driver_id,))
        ).fetchone()
    return json.loads(row[0]) if row else {}
