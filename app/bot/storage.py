from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite


@dataclass(slots=True)
class DriverLink:
    telegram_user_id: int
    driver_id: str
    phone: str | None
    username: str | None
    first_name: str | None
    last_name: str | None
    linked_at: str
    updated_at: str


class DriverLinkStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS telegram_driver_links (
                    telegram_user_id INTEGER PRIMARY KEY,
                    driver_id TEXT NOT NULL UNIQUE,
                    phone TEXT,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    linked_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_telegram_driver_links_driver_id
                ON telegram_driver_links(driver_id)
                """
            )
            await db.commit()

    async def get(self, telegram_user_id: int) -> DriverLink | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT telegram_user_id, driver_id, phone, username,
                       first_name, last_name, linked_at, updated_at
                FROM telegram_driver_links
                WHERE telegram_user_id = ?
                """,
                (telegram_user_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return DriverLink(**dict(row))

    async def get_driver_id(self, telegram_user_id: int) -> str | None:
        link = await self.get(telegram_user_id)
        return link.driver_id if link else None

    async def link(
        self,
        *,
        telegram_user_id: int,
        driver_id: str,
        phone: str | None,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> DriverLink:
        now = datetime.now(UTC).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            # One driver account may be bound to only one Telegram user at a time.
            # Linking from a new Telegram account transfers the binding.
            await db.execute(
                """
                DELETE FROM telegram_driver_links
                WHERE driver_id = ? AND telegram_user_id <> ?
                """,
                (driver_id, telegram_user_id),
            )
            await db.execute(
                """
                INSERT INTO telegram_driver_links (
                    telegram_user_id, driver_id, phone, username,
                    first_name, last_name, linked_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    driver_id = excluded.driver_id,
                    phone = excluded.phone,
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    updated_at = excluded.updated_at
                """,
                (
                    telegram_user_id,
                    driver_id,
                    phone,
                    username,
                    first_name,
                    last_name,
                    now,
                    now,
                ),
            )
            await db.commit()

        link = await self.get(telegram_user_id)
        if link is None:
            raise RuntimeError("Не удалось сохранить привязку Telegram.")
        return link

    async def unlink(self, telegram_user_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM telegram_driver_links WHERE telegram_user_id = ?",
                (telegram_user_id,),
            )
            await db.commit()
            return cursor.rowcount > 0
