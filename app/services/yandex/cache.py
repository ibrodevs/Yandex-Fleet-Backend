from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import aiosqlite

from app.core.exceptions import YandexApiError, YandexAuthError, YandexRateLimitError
from app.core.logging import get_logger, log_event

logger = get_logger(__name__)
T = TypeVar("T")


@dataclass(slots=True)
class CacheEntry:
    payload: Any
    updated_at: float


class SharedYandexCache:
    """SQLite snapshots with file-lock single-flight shared by local processes."""

    def __init__(
        self,
        db_path: str,
        *,
        clock: Callable[[], float] = time.time,
        sqlite_timeout: float = 30,
    ) -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.lock_dir = self.db_path.parent / f".{self.db_path.name}.locks"
        self.clock = clock
        self.sqlite_timeout = sqlite_timeout
        self._schema_ready = False

    async def _connect(self) -> aiosqlite.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        schema_lock = None
        if not self._schema_ready:
            schema_lock = await asyncio.to_thread(self._acquire_lock, "__schema__")
        db: aiosqlite.Connection | None = None
        try:
            db = await aiosqlite.connect(self.db_path, timeout=self.sqlite_timeout)
            await db.execute(f"PRAGMA busy_timeout={int(self.sqlite_timeout * 1000)}")
            if not self._schema_ready:
                row = await (
                    await db.execute(
                        "SELECT 1 FROM sqlite_master "
                        "WHERE type='table' AND name='yandex_cache'"
                    )
                ).fetchone()
                if row is None:
                    await db.execute("PRAGMA journal_mode=WAL")
                    await db.execute(
                        """
                        CREATE TABLE yandex_cache (
                            cache_key TEXT PRIMARY KEY,
                            payload TEXT NOT NULL,
                            updated_at REAL NOT NULL
                        )
                        """
                    )
                    await db.commit()
                self._schema_ready = True
            return db
        except Exception:
            if db is not None:
                await db.close()
            raise
        finally:
            if schema_lock is not None:
                await asyncio.to_thread(self._release_lock, schema_lock)

    async def get(self, cache_key: str) -> CacheEntry | None:
        db = await self._connect()
        try:
            row = await (
                await db.execute(
                    "SELECT payload, updated_at FROM yandex_cache WHERE cache_key=?",
                    (cache_key,),
                )
            ).fetchone()
        finally:
            await db.close()
        if not row:
            return None
        try:
            payload = json.loads(row[0])
        except (TypeError, ValueError):
            log_event(
                logger,
                "yandex_cache_refresh_failed",
                level="warning",
                cache_key=cache_key,
                error_type="InvalidCachedJson",
            )
            return None
        return CacheEntry(payload=payload, updated_at=float(row[1]))

    async def set(self, cache_key: str, payload: Any) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        db = await self._connect()
        try:
            await db.execute(
                """
                INSERT INTO yandex_cache(cache_key, payload, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (cache_key, encoded, self.clock()),
            )
            await db.commit()
        finally:
            await db.close()

    def _lock_path(self, cache_key: str) -> Path:
        digest = hashlib.sha256(cache_key.encode()).hexdigest()[:24]
        return self.lock_dir / f"{digest}.lock"

    def _acquire_lock(self, cache_key: str):
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        handle = self._lock_path(cache_key).open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except Exception:
            handle.close()
            raise
        return handle

    @staticmethod
    def _release_lock(handle) -> None:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    @asynccontextmanager
    async def refresh_lock(self, cache_key: str):
        started = time.monotonic()
        handle = await asyncio.to_thread(self._acquire_lock, cache_key)
        waited_ms = round((time.monotonic() - started) * 1000)
        log_event(
            logger,
            "yandex_cache_lock_wait",
            cache_key=cache_key,
            duration_ms=waited_ms,
        )
        try:
            yield
        finally:
            await asyncio.to_thread(self._release_lock, handle)

    def _age(self, entry: CacheEntry) -> float:
        return max(0.0, self.clock() - entry.updated_at)

    @staticmethod
    def _temporary_error(exc: Exception) -> bool:
        return isinstance(exc, YandexRateLimitError) or (
            isinstance(exc, YandexApiError) and exc.status_code >= 500
        )

    async def get_or_refresh(
        self,
        cache_key: str,
        *,
        ttl_seconds: float,
        stale_seconds: float,
        refresh: Callable[[], Awaitable[T]],
        stale_refresh: Callable[[], Awaitable[T]] | None = None,
    ) -> T:
        entry = await self.get(cache_key)
        age = self._age(entry) if entry else None
        if entry and age is not None and age <= ttl_seconds:
            log_event(
                logger,
                "yandex_cache_hit",
                cache_key=cache_key,
                age_seconds=round(age, 3),
                ttl_seconds=ttl_seconds,
            )
            return entry.payload

        log_event(
            logger,
            "yandex_cache_miss",
            cache_key=cache_key,
            age_seconds=round(age, 3) if age is not None else None,
            ttl_seconds=ttl_seconds,
        )
        async with self.refresh_lock(cache_key):
            locked_entry = await self.get(cache_key)
            locked_age = self._age(locked_entry) if locked_entry else None
            if locked_entry and locked_age is not None and locked_age <= ttl_seconds:
                log_event(
                    logger,
                    "yandex_cache_hit",
                    cache_key=cache_key,
                    age_seconds=round(locked_age, 3),
                    ttl_seconds=ttl_seconds,
                )
                return locked_entry.payload

            started = time.monotonic()
            log_event(
                logger,
                "yandex_cache_refresh_started",
                cache_key=cache_key,
                age_seconds=round(locked_age, 3) if locked_age is not None else None,
                ttl_seconds=ttl_seconds,
            )
            can_serve_stale = bool(
                locked_entry
                and locked_age is not None
                and locked_age <= ttl_seconds + stale_seconds
            )
            refresh_call = stale_refresh if can_serve_stale and stale_refresh else refresh
            try:
                payload = await refresh_call()
            except YandexAuthError as exc:
                log_event(
                    logger,
                    "yandex_cache_refresh_failed",
                    level="error",
                    cache_key=cache_key,
                    duration_ms=round((time.monotonic() - started) * 1000),
                    error_type=type(exc).__name__,
                )
                raise
            except (YandexApiError, YandexRateLimitError) as exc:
                log_event(
                    logger,
                    "yandex_cache_refresh_failed",
                    level="warning",
                    cache_key=cache_key,
                    duration_ms=round((time.monotonic() - started) * 1000),
                    error_type=type(exc).__name__,
                )
                if (
                    can_serve_stale
                    and locked_entry
                    and self._temporary_error(exc)
                ):
                    log_event(
                        logger,
                        "yandex_cache_stale_served",
                        level="warning",
                        cache_key=cache_key,
                        age_seconds=round(locked_age, 3),
                        ttl_seconds=ttl_seconds,
                        error_type=type(exc).__name__,
                    )
                    return locked_entry.payload
                raise

            await self.set(cache_key, payload)
            log_event(
                logger,
                "yandex_cache_refresh_completed",
                cache_key=cache_key,
                duration_ms=round((time.monotonic() - started) * 1000),
                ttl_seconds=ttl_seconds,
            )
            return payload
