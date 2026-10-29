"""玩家数据刷新：合并同一 UID 的并发请求并写入本地快照。"""

import time
import asyncio
from dataclasses import dataclass

import httpx

from ..api.dakanu import DakanuProfile, fetch_clan, fetch_leisure, refresh_profile
from .player_data import PlayerSnapshot, has_player_data, load_player_snapshot, save_player_snapshot


@dataclass(frozen=True)
class RefreshResult:
    player_id: str
    snapshot: PlayerSnapshot
    from_cache: bool


_locks: dict[str, asyncio.Lock] = {}
_inflight: dict[str, asyncio.Task[RefreshResult]] = {}
_background_tasks: set[asyncio.Task[object]] = set()


def _lock_for(player_id: str) -> asyncio.Lock:
    lock = _locks.get(player_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[player_id] = lock
    return lock


def track_background(task: asyncio.Task[object]) -> None:
    """持有后台任务强引用，避免事件循环只保留弱引用时被回收。"""
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _snapshot_from_profile(player_id: str, profile: DakanuProfile) -> PlayerSnapshot:
    leisure = await fetch_leisure(player_id)
    clan = await fetch_clan(profile["player"]["clanId"])
    snapshot = PlayerSnapshot(
        profile=profile,
        leisure=leisure,
        clan=clan,
        saved_at=int(time.time()),
    )
    await save_player_snapshot(snapshot)
    return snapshot


async def _refresh_uncached(player_id: str) -> RefreshResult:
    try:
        profile = await refresh_profile(player_id)
        snapshot = await _snapshot_from_profile(player_id, profile)
    except (httpx.HTTPError, OSError) as exc:
        raise RuntimeError("连接战绩站失败，请稍后重试。") from exc
    return RefreshResult(player_id=player_id, snapshot=snapshot, from_cache=False)


async def refresh_player_data(player_id: str, *, force: bool = False) -> RefreshResult:
    """读取或刷新玩家数据；force=False 时优先使用本地快照。"""
    inflight = _inflight.get(player_id)
    if inflight is not None:
        return await asyncio.shield(inflight)

    lock = _lock_for(player_id)
    async with lock:
        inflight = _inflight.get(player_id)
        if inflight is not None:
            return await asyncio.shield(inflight)
        if not force:
            snapshot = await load_player_snapshot(player_id)
            if snapshot is not None and has_player_data(player_id):
                return RefreshResult(player_id=player_id, snapshot=snapshot, from_cache=True)

        task = asyncio.create_task(_refresh_uncached(player_id))
        _inflight[player_id] = task
        try:
            return await asyncio.shield(task)
        finally:
            if _inflight.get(player_id) is task:
                _inflight.pop(player_id, None)
