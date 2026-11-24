"""通用异步 LRU/TTL 内存缓存，支持按 key 合并在途请求。"""

import time
import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from collections.abc import Callable, Hashable, Awaitable


@dataclass(frozen=True, slots=True)
class CacheHit[ValueT]:
    value: ValueT


@dataclass(frozen=True, slots=True)
class _CacheEntry[ValueT]:
    value: ValueT
    expires_at: float | None


class AsyncTtlCache[KeyT: Hashable, ValueT]:
    """带容量淘汰、可选 TTL 与单飞合并的异步内存缓存。"""

    def __init__(self, *, maxsize: int = 256, ttl_seconds: float | None = None) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive or None")
        self._maxsize = maxsize
        self._ttl_seconds = ttl_seconds
        self._entries: OrderedDict[KeyT, _CacheEntry[ValueT]] = OrderedDict()
        self._inflight: dict[KeyT, asyncio.Task[ValueT]] = {}

    def _is_expired(self, entry: _CacheEntry[ValueT], now: float) -> bool:
        return entry.expires_at is not None and now >= entry.expires_at

    def _get_entry(self, key: KeyT) -> _CacheEntry[ValueT] | None:
        if key not in self._entries:
            return None
        entry = self._entries[key]
        if self._is_expired(entry, time.monotonic()):
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return entry

    def get(self, key: KeyT) -> CacheHit[ValueT] | None:
        entry = self._get_entry(key)
        if entry is None:
            return None
        return CacheHit(value=entry.value)

    def set(self, key: KeyT, value: ValueT, *, ttl_seconds: float | None = None) -> None:
        effective_ttl = self._ttl_seconds if ttl_seconds is None else ttl_seconds
        expires_at = (time.monotonic() + effective_ttl) if effective_ttl is not None else None
        self._entries[key] = _CacheEntry(value=value, expires_at=expires_at)
        self._entries.move_to_end(key)
        while len(self._entries) > self._maxsize:
            self._entries.popitem(last=False)

    def delete(self, key: KeyT) -> None:
        if key in self._entries:
            del self._entries[key]

    def clear(self) -> None:
        self._entries.clear()

    async def get_or_load(
        self,
        key: KeyT,
        loader: Callable[[], Awaitable[ValueT]],
        *,
        should_cache: Callable[[ValueT], bool] | None = None,
        use_cache: bool = True,
    ) -> ValueT:
        if use_cache:
            entry = self._get_entry(key)
            if entry is not None:
                return entry.value

        if key in self._inflight:
            return await asyncio.shield(self._inflight[key])

        async def _run() -> ValueT:
            value = await loader()
            if should_cache is None or should_cache(value):
                self.set(key, value)
            return value

        task = asyncio.create_task(_run())
        self._inflight[key] = task

        def _cleanup(finished: asyncio.Task[ValueT]) -> None:
            if key in self._inflight and self._inflight[key] is finished:
                del self._inflight[key]
            if not finished.cancelled():
                finished.exception()

        task.add_done_callback(_cleanup)
        return await asyncio.shield(task)
