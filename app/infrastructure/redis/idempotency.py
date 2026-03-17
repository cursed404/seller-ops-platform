import redis


class IdempotencyStore:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def acquire(self, key: str, ttl_seconds: int = 3600) -> bool:
        return bool(self._client.set(name=key, value="1", nx=True, ex=ttl_seconds))

    def exists(self, key: str) -> bool:
        return bool(self._client.exists(key))

