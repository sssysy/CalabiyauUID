"""玩家数据刷新：合并同一 UID 的并发请求并写入本地快照。"""

import time
import asyncio
from dataclasses import dataclass
from collections.abc import Callable, Awaitable

import httpx

from gsuid_core.bot import Bot
from gsuid_core.logger import logger

from ..api.dakanu import DakanuError, DakanuProfile, fetch_clan, fetch_leisure, refresh_profile
from .player_data import PlayerSnapshot, has_player_data, load_player_snapshot, save_player_snapshot
from ..utils.cache import KeyedLockPool
from ..utils.background import track_background_task

_SNAPSHOT_TTL_SECONDS = 86400
_AUTO_REFRESH_WAIT_SECONDS = 10.0
BUSY_FALLBACK_NOTICE = "拉取最新数据繁忙，将显示缓存数据。最新数据待拉取成功后展示"


@dataclass(frozen=True)
class RefreshResult:
    player_id: str
    snapshot: PlayerSnapshot
    from_cache: bool


@dataclass(frozen=True)
class SnapshotFetchResult:
    snapshot: PlayerSnapshot
    pending_task: asyncio.Task[RefreshResult] | None = None


def is_snapshot_expired(snapshot: PlayerSnapshot) -> bool:
    """判断本地快照是否已满或超过 1 天。"""
    return int(time.time()) - snapshot.saved_at >= _SNAPSHOT_TTL_SECONDS


_locks: KeyedLockPool[str] = KeyedLockPool()
_inflight: dict[str, asyncio.Task[RefreshResult]] = {}


async def _snapshot_from_profile(player_id: str, profile: DakanuProfile) -> PlayerSnapshot:
    leisure, clan = await asyncio.gather(
        fetch_leisure(player_id),
        fetch_clan(profile["player"]["clanId"]),
    )
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


async def _load_valid_local_snapshot(player_id: str) -> PlayerSnapshot | None:
    snapshot = await load_player_snapshot(player_id)
    if snapshot is None or not has_player_data(player_id):
        return None
    return snapshot


async def _get_or_start_refresh_task(
    player_id: str,
    *,
    force: bool,
) -> tuple[PlayerSnapshot | None, asyncio.Task[RefreshResult] | None]:
    """返回 (可用本地快照, 正在执行的刷新任务)；未过期且非强制时任务为 None。"""
    if player_id in _inflight:
        cached = None if force else await _load_valid_local_snapshot(player_id)
        return cached, _inflight[player_id]

    async with _locks.acquire(player_id):
        if player_id in _inflight:
            cached = None if force else await _load_valid_local_snapshot(player_id)
            return cached, _inflight[player_id]

        cached: PlayerSnapshot | None = None
        if not force:
            snapshot = await _load_valid_local_snapshot(player_id)
            if snapshot is not None:
                if not is_snapshot_expired(snapshot):
                    return snapshot, None
                cached = snapshot

        task = asyncio.create_task(_refresh_uncached(player_id))
        _inflight[player_id] = task
        track_background_task(task)

        def _on_done(finished: asyncio.Task[RefreshResult]) -> None:
            if player_id in _inflight and _inflight[player_id] is finished:
                del _inflight[player_id]
            if not finished.cancelled():
                finished.exception()

        task.add_done_callback(_on_done)
        return cached, task


async def refresh_player_data(player_id: str, *, force: bool = False) -> RefreshResult:
    """读取或刷新玩家数据；force=False 时优先使用 1 天内的本地快照。"""
    cached, task = await _get_or_start_refresh_task(player_id, force=force)
    if task is None and cached is not None:
        return RefreshResult(player_id=player_id, snapshot=cached, from_cache=True)
    if task is None:
        raise RuntimeError("未能启动玩家数据刷新任务。")
    return await asyncio.shield(task)


async def ensure_player_snapshot(player_id: str, *, force: bool = False) -> PlayerSnapshot:
    """获取 1 天内有效的玩家快照；本地无快照或已超期时静默拉取。"""
    try:
        result = await refresh_player_data(player_id, force=force)
    except RuntimeError as exc:
        raise DakanuError(str(exc)) from exc
    return result.snapshot


async def ensure_player_snapshot_with_fallback(
    player_id: str,
    *,
    wait_seconds: float = _AUTO_REFRESH_WAIT_SECONDS,
) -> SnapshotFetchResult:
    """获取玩家快照；本地过期且自动刷新超过 wait_seconds 时先返回旧缓存与后台任务。"""
    cached, task = await _get_or_start_refresh_task(player_id, force=False)
    if task is None and cached is not None:
        return SnapshotFetchResult(snapshot=cached, pending_task=None)
    if task is None:
        raise DakanuError("未能获取玩家战绩快照，请稍后再试。")

    if cached is None:
        try:
            result = await asyncio.shield(task)
        except RuntimeError as exc:
            raise DakanuError(str(exc)) from exc
        return SnapshotFetchResult(snapshot=result.snapshot, pending_task=None)

    try:
        result = await asyncio.wait_for(asyncio.shield(task), timeout=wait_seconds)
    except TimeoutError:
        return SnapshotFetchResult(snapshot=cached, pending_task=task)
    except RuntimeError as exc:
        raise DakanuError(str(exc)) from exc
    return SnapshotFetchResult(snapshot=result.snapshot, pending_task=None)


def schedule_refreshed_card_push(
    bot: Bot,
    pending_task: asyncio.Task[RefreshResult],
    render_fn: Callable[[PlayerSnapshot], Awaitable[bytes | None]],
    *,
    feature_name: str,
    player_id: str,
) -> None:
    """等待后台刷新完成后重渲染卡片并 @ 用户推送；失败时静默记日志。"""

    async def _push_when_ready() -> None:
        try:
            result = await asyncio.shield(pending_task)
        except (DakanuError, RuntimeError) as exc:
            logger.warning(f"[卡拉彼丘·{feature_name}] 玩家 {player_id} 后台刷新失败：{exc}")
            return
        try:
            image = await render_fn(result.snapshot)
        except (DakanuError, RuntimeError) as exc:
            logger.warning(f"[卡拉彼丘·{feature_name}] 玩家 {player_id} 最新卡片渲染失败：{exc}")
            return
        if image is None:
            return
        await bot.send(image, at_sender=True)

    task = asyncio.create_task(_push_when_ready())
    track_background_task(task)
