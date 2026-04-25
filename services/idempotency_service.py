import time
import logging
import redis

from config import settings

logger = logging.getLogger(__name__)


class IdempotencyService:
    def __init__(self):
        self._client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            socket_timeout=settings.redis_timeout,
            decode_responses=True,
        )

    def claim(self, packet_hash: str) -> bool:
        key = f"idempotency:{packet_hash}"
        result = self._client.set(
            key, str(time.time()), nx=True, ex=settings.idempotency_ttl_seconds
        )
        return result is True

    def size(self) -> int:
        return len(self._client.keys("idempotency:*"))

    def clear(self) -> None:
        keys = self._client.keys("idempotency:*")
        if keys:
            self._client.delete(*keys)


idempotency_service = IdempotencyService()
