"""通用异步 LRU/TTL 内存缓存、按 key 锁池与磁盘缓存保活工具。"""

import os
import time
import asyncio
from typing import Protocol
from pathlib import Path
from weakref import WeakSet
from contextlib import asynccontextmanager
from collections import OrderedDict
from dataclasses import dataclass
from collections.abc import Callable, Hashable, Awaitable, AsyncIterator


class ManagedMemoryCache(Protocol):
    """由统一缓存中心管理过期回收与关机收尾的内存缓存协议。"""

    def purge_expired(self) -> int: ...
    async def close(self) -> None: ...


_registered_caches: WeakSet[ManagedMemoryCache] = WeakSet()


def purge_registered_memory_caches() -> int:
    """主动清理所有已登记内存缓存中的过期条目，返回移除总数。"""
    removed = 0
    for cache in list(_registered_caches):
        removed += cache.purge_expired()
    return removed


async def close_registered_memory_caches() -> None:
    """关闭所有已登记内存缓存，取消在途加载任务并清空缓存。"""
    for cache in list(_registered_caches):
        await cache.close()


def touch_cache_mtime(path: Path, *, min_interval_seconds: float = 3600.0) -> None:
    """节流更新缓存文件修改时间，避免高频命中时反复写磁盘元数据。"""
    try:
        mtime = path.stat().st_mtime
        if min_interval_seconds <= 0 or (time.time() - mtime) >= min_interval_seconds:
            os.utime(path, None)
    except OSError:
        pass


@dataclass(slots=True)
class _KeyedLockEntry:
    lock: asyncio.Lock
    waiters: int = 0


class KeyedLockPool[KeyT: Hashable]:
    """按 key 隔离的异步锁池，无等待协程时立即回收条目。"""

    def __init__(self) -> None:
        self._entries: dict[KeyT, _KeyedLockEntry] = {}

    @asynccontextmanager
    async def acquire(self, key: KeyT) -> AsyncIterator[None]:
        if key not in self._entries:
            self._entries[key] = _KeyedLockEntry(lock=asyncio.Lock())
        entry = self._entries[key]
        entry.waiters += 1
        try:
            async with entry.lock:
                yield
        finally:
            entry.waiters -= 1
            if entry.waiters <= 0 and key in self._entries and self._entries[key] is entry:
                del self._entries[key]

    def __len__(self) -> int:
        return len(self._entries)


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
        _registered_caches.add(self)

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

    def purge_expired(self) -> int:
        now = time.monotonic()
        expired_keys = [key for key, entry in self._entries.items() if self._is_expired(entry, now)]
        for key in expired_keys:
            del self._entries[key]
        return len(expired_keys)

    async def close(self) -> None:
        tasks = list(self._inflight.values())
        self._inflight.clear()
        self._entries.clear()
        pending = [task for task in tasks if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

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
