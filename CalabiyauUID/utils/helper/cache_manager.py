"""统一缓存清理定时任务与停机生命周期收尾中心。"""

import time
from pathlib import Path
from dataclasses import dataclass

from gsuid_core.aps import scheduler
from gsuid_core.pool import to_thread
from gsuid_core.logger import logger
from gsuid_core.server import on_core_shutdown

from ..utils.cache import close_registered_memory_caches, purge_registered_memory_caches
from ..utils.paths import (
    IMG_CACHE_DIR,
    REPLAY_CACHE_DIR,
    MATCH_STATS_CACHE_DIR,
    MATCH_DETAIL_CACHE_DIR,
)
from ..utils.background import cancel_all_background_tasks
from ...calabiyau_config import CalabiyauConfig
from ..api.dakanu.client import close_dakanu_client

_LOG_TAG = "[卡拉彼丘·缓存清理]"
_SECONDS_PER_DAY = 86400.0
_TMP_ORPHAN_SECONDS = 3600.0
_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})


@dataclass(frozen=True, slots=True)
class DiskCacheRule:
    name: str
    directory: Path
    suffixes: frozenset[str]
    max_files: int | None = None


@dataclass(frozen=True, slots=True)
class CacheCleanupReport:
    memory_entries_removed: int
    disk_files_removed: int
    disk_bytes_freed: int


_DISK_CACHE_RULES: tuple[DiskCacheRule, ...] = (
    DiskCacheRule(
        name="replay",
        directory=REPLAY_CACHE_DIR,
        suffixes=frozenset({".replay"}),
    ),
    DiskCacheRule(
        name="img_cache",
        directory=IMG_CACHE_DIR,
        suffixes=_IMAGE_SUFFIXES,
    ),
    DiskCacheRule(
        name="match_detail",
        directory=MATCH_DETAIL_CACHE_DIR,
        suffixes=frozenset({".json"}),
        max_files=300,
    ),
    DiskCacheRule(
        name="match_stats",
        directory=MATCH_STATS_CACHE_DIR,
        suffixes=frozenset({".json"}),
        max_files=100,
    ),
)


def _read_clean_days() -> int:
    raw: object = CalabiyauConfig.get_config("CacheCleanDays").data
    if isinstance(raw, int) and not isinstance(raw, bool):
        return max(raw, 0)
    return 3


def _unlink_file_safely(path: Path) -> int | None:
    try:
        size = path.stat().st_size
        path.unlink(missing_ok=True)
        return size
    except OSError as exc:
        logger.debug(f"{_LOG_TAG} 跳过无法删除的缓存文件 {path.name}：{exc}")
        return None


def _cleanup_disk_rule_sync(rule: DiskCacheRule, *, now: float, max_age_seconds: float | None) -> tuple[int, int]:
    if not rule.directory.is_dir():
        return 0, 0

    removed_count = 0
    freed_bytes = 0
    retained: list[tuple[float, Path]] = []

    try:
        items = list(rule.directory.iterdir())
    except OSError as exc:
        logger.warning(f"{_LOG_TAG} 遍历缓存目录 {rule.name} 失败：{exc}")
        return 0, 0

    for item in items:
        if not item.is_file():
            continue
        try:
            mtime = item.stat().st_mtime
        except OSError:
            continue

        age = now - mtime
        suffix = item.suffix.lower()
        if suffix == ".tmp":
            if age >= _TMP_ORPHAN_SECONDS:
                freed = _unlink_file_safely(item)
                if freed is not None:
                    removed_count += 1
                    freed_bytes += freed
            continue

        if suffix not in rule.suffixes:
            continue

        if max_age_seconds is not None and age >= max_age_seconds:
            freed = _unlink_file_safely(item)
            if freed is not None:
                removed_count += 1
                freed_bytes += freed
            continue

        retained.append((mtime, item))

    if rule.max_files is not None and len(retained) > rule.max_files:
        retained.sort(key=lambda pair: pair[0])
        excess = len(retained) - rule.max_files
        for _, stale_path in retained[:excess]:
            freed = _unlink_file_safely(stale_path)
            if freed is not None:
                removed_count += 1
                freed_bytes += freed

    return removed_count, freed_bytes


def _cleanup_all_disk_caches_sync(days: int) -> tuple[int, int]:
    now = time.time()
    max_age_seconds = days * _SECONDS_PER_DAY if days > 0 else None
    total_files = 0
    total_bytes = 0
    for rule in _DISK_CACHE_RULES:
        files, freed = _cleanup_disk_rule_sync(rule, now=now, max_age_seconds=max_age_seconds)
        total_files += files
        total_bytes += freed
    return total_files, total_bytes


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.2f} MB"


async def run_cache_cleanup() -> CacheCleanupReport:
    """执行一轮统一缓存清理：回收内存过期项并按配置清理磁盘缓存。"""
    memory_removed = purge_registered_memory_caches()
    days = _read_clean_days()
    disk_files, disk_bytes = await to_thread(_cleanup_all_disk_caches_sync)(days)
    if memory_removed > 0 or disk_files > 0:
        logger.info(
            f"{_LOG_TAG} 本轮清理完成：内存过期条目 {memory_removed} 项，"
            f"磁盘文件 {disk_files} 个（释放 {_format_bytes(disk_bytes)}，过期阈值 {days} 天）"
        )
    else:
        logger.debug(f"{_LOG_TAG} 本轮巡检无可清理缓存（过期阈值 {days} 天）")
    return CacheCleanupReport(
        memory_entries_removed=memory_removed,
        disk_files_removed=disk_files,
        disk_bytes_freed=disk_bytes,
    )


@scheduler.scheduled_job("interval", hours=1, id="klbq_cache_cleanup", replace_existing=True)
async def scheduled_cache_cleanup() -> None:
    await run_cache_cleanup()


@on_core_shutdown
async def shutdown_calabiyau_runtime() -> None:
    """停机或热重载时统一取消后台任务并释放内存缓存。"""
    cancelled_tasks = await cancel_all_background_tasks()
    await close_registered_memory_caches()
    await close_dakanu_client()
    if cancelled_tasks > 0:
        logger.info(f"{_LOG_TAG} 停机收尾已取消 {cancelled_tasks} 个后台任务并释放内存缓存")
