import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_redis_client: Redis | None = None


def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
        )
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


class DistributedLock:
    """
    Redis-backed distributed lock with safe token release via Lua script.
    Prevents concurrent executions across workers.
    """

    RELEASE_LUA = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """

    def __init__(
        self,
        redis_client: Redis,
        name: str,
        timeout_seconds: int = 60,
        blocking: bool = False,
        blocking_timeout: float = 0.0,
    ):
        self.redis = redis_client
        self.key = f"lock:{name}"
        self.timeout = timeout_seconds
        self.blocking = blocking
        self.blocking_timeout = blocking_timeout
        self.token = str(uuid.uuid4())
        self.acquired = False

    async def acquire(self) -> bool:
        start_time = asyncio.get_event_loop().time()
        while True:
            # Set key if Not eXists with EXpiration
            res = await self.redis.set(self.key, self.token, nx=True, ex=self.timeout)
            if res:
                self.acquired = True
                return True

            if not self.blocking:
                return False

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= self.blocking_timeout:
                return False

            await asyncio.sleep(0.1)

    async def release(self) -> None:
        if not self.acquired:
            return
        try:
            await self.redis.eval(self.RELEASE_LUA, 1, self.key, self.token)
        except Exception as e:
            logger.warning("Failed to release lock %s cleanly: %s", self.key, e)
        finally:
            self.acquired = False

    async def __aenter__(self) -> bool:
        return await self.acquire()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.release()


async def publish_event(channel: str, event_type: str, data: Any) -> int:
    """Publish a real-time event to a Redis Pub/Sub channel."""
    redis = get_redis()
    payload = json.dumps(
        {
            "type": event_type,
            "data": data,
        },
        default=str,
    )
    receivers = await redis.publish(channel, payload)
    return receivers


async def subscribe_channel(channel: str) -> AsyncGenerator[dict, None]:
    """Subscribe to a Redis Pub/Sub channel and yield deserialized messages."""
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    payload = json.loads(message["data"])
                    yield payload
                except json.JSONDecodeError:
                    continue
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
