import asyncio
import multiprocessing
import time

import pytest

from app.core.exceptions import YandexApiError, YandexAuthError, YandexRateLimitError
from app.services.yandex.cache import SharedYandexCache


class Clock:
    def __init__(self, value: float = 100.0):
        self.value = value

    def __call__(self) -> float:
        return self.value


def _hold_lock(db_path: str, name: str, hold_seconds: float, events) -> None:
    async def run() -> None:
        cache = SharedYandexCache(db_path)
        async with cache.refresh_lock("orders:park:default"):
            events.put((name, "entered", time.monotonic()))
            await asyncio.sleep(hold_seconds)
            events.put((name, "leaving", time.monotonic()))

    asyncio.run(run())


@pytest.mark.asyncio
async def test_cache_hit_and_expiry(tmp_path):
    clock = Clock()
    cache = SharedYandexCache(str(tmp_path / "cache.sqlite3"), clock=clock)
    calls = 0

    async def refresh():
        nonlocal calls
        calls += 1
        return [{"version": calls}]

    first = await cache.get_or_refresh(
        "drivers:park:default",
        ttl_seconds=10,
        stale_seconds=60,
        refresh=refresh,
    )
    clock.value += 5
    second = await cache.get_or_refresh(
        "drivers:park:default",
        ttl_seconds=10,
        stale_seconds=60,
        refresh=refresh,
    )
    clock.value += 6
    third = await cache.get_or_refresh(
        "drivers:park:default",
        ttl_seconds=10,
        stale_seconds=60,
        refresh=refresh,
    )

    assert first == second == [{"version": 1}]
    assert third == [{"version": 2}]
    assert calls == 2


@pytest.mark.asyncio
async def test_concurrent_cache_instances_single_flight_refresh(tmp_path):
    db_path = str(tmp_path / "cache.sqlite3")
    caches = [SharedYandexCache(db_path) for _ in range(5)]
    calls = 0

    async def refresh():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return [{"id": "one"}]

    results = await asyncio.gather(
        *[
            cache.get_or_refresh(
                "orders:park:default",
                ttl_seconds=10,
                stale_seconds=60,
                refresh=refresh,
            )
            for cache in caches
        ]
    )

    assert results == [[{"id": "one"}]] * 5
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        YandexRateLimitError(),
        YandexApiError("timeout", status_code=504),
    ],
)
async def test_temporary_refresh_error_serves_bounded_stale_cache(tmp_path, error):
    clock = Clock()
    cache = SharedYandexCache(str(tmp_path / "cache.sqlite3"), clock=clock)
    await cache.set("orders:park:default", [{"id": "cached"}])
    clock.value += 17

    async def refresh():
        raise error

    result = await cache.get_or_refresh(
        "orders:park:default",
        ttl_seconds=10,
        stale_seconds=60,
        refresh=refresh,
    )
    assert result == [{"id": "cached"}]


@pytest.mark.asyncio
async def test_too_old_cache_and_auth_errors_are_not_hidden(tmp_path):
    clock = Clock()
    cache = SharedYandexCache(str(tmp_path / "cache.sqlite3"), clock=clock)
    await cache.set("orders:park:default", [{"id": "cached"}])

    async def rate_limited():
        raise YandexRateLimitError()

    clock.value += 71
    with pytest.raises(YandexRateLimitError):
        await cache.get_or_refresh(
            "orders:park:default",
            ttl_seconds=10,
            stale_seconds=60,
            refresh=rate_limited,
        )

    clock.value = 105

    async def unauthorized():
        raise YandexAuthError()

    with pytest.raises(YandexAuthError):
        await cache.get_or_refresh(
            "orders:park:default",
            ttl_seconds=1,
            stale_seconds=60,
            refresh=unauthorized,
        )


def test_file_lock_serializes_separate_processes(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    events = ctx.Queue()
    db_path = str(tmp_path / "cache.sqlite3")
    first = ctx.Process(target=_hold_lock, args=(db_path, "first", 0.3, events))
    second = ctx.Process(target=_hold_lock, args=(db_path, "second", 0.0, events))

    first.start()
    first_entered = events.get(timeout=5)
    second.start()
    remaining = [events.get(timeout=5) for _ in range(3)]
    first.join(timeout=5)
    second.join(timeout=5)

    all_events = [first_entered, *remaining]
    timestamps = {(name, event): timestamp for name, event, timestamp in all_events}
    assert first_entered[:2] == ("first", "entered")
    assert timestamps[("second", "entered")] >= timestamps[("first", "leaving")]
    assert first.exitcode == second.exitcode == 0
