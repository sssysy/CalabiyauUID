"""启动后从资源仓库同步静态资源。"""

import os
import re
import stat
import shutil
import asyncio
from pathlib import Path
from dataclasses import dataclass
from collections.abc import Callable

from gsuid_core.logger import logger
from gsuid_core.server import on_core_start
from gsuid_core.utils.plugins_update.git_async import (
    GIT_CLONE_TIMEOUT,
    run_git,
    git_clone,
    git_reset_hard,
    git_get_remote_url,
    git_set_remote_url,
    git_get_current_commit,
)

from .maps import reload_maps_data
from ..utils.paths import RESOURCE_DIR

RESOURCE_REPO_URL = "https://cnb.cool/shiysssysy/CalabiyauUID-resourse"
_RESOURCE_TAG = "[卡拉彼丘·资源更新]"
_PROBE_TIMEOUT = 5
_STAGING_DIR = RESOURCE_DIR.with_name(f"{RESOURCE_DIR.name}-staging")
_update_lock = asyncio.Lock()


@dataclass(frozen=True)
class _SyncOutcome:
    success: bool
    changed: bool


def _parse_default_branch(stdout: str) -> str | None:
    match = re.search(r"ref:\s+refs/heads/(\S+)", stdout)
    return match.group(1) if match is not None else None


def _is_git_repo() -> bool:
    return (RESOURCE_DIR / ".git").is_dir()


def _retry_writable(func: Callable[[str], None], target: str, _exc: BaseException) -> None:
    # git pack 文件只读，Windows 上必须先去掉只读位再删
    os.chmod(target, stat.S_IWRITE)
    func(target)


def _drop_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onexc=_retry_writable)


async def _resolve_default_branch() -> str | None:
    retcode, stdout, stderr = await run_git(
        RESOURCE_DIR,
        "ls-remote",
        "--symref",
        RESOURCE_REPO_URL,
        "HEAD",
        timeout=_PROBE_TIMEOUT,
    )
    if retcode != 0:
        logger.warning(f"{_RESOURCE_TAG} 探测仓库默认分支失败：{stderr or 'timeout'}")
        return None
    branch = _parse_default_branch(stdout)
    if branch is None:
        logger.warning(f"{_RESOURCE_TAG} 仓库未返回默认分支")
        return None
    return branch


async def _clone_from(branch: str) -> _SyncOutcome:
    # 目录已有旧素材但不是 git 仓库时，git clone 会拒绝写入非空目录
    await asyncio.to_thread(_drop_dir, _STAGING_DIR)
    success, message = await git_clone(
        RESOURCE_REPO_URL,
        _STAGING_DIR,
        branch=branch,
        depth=1,
        timeout=GIT_CLONE_TIMEOUT,
    )
    if not success:
        logger.warning(f"{_RESOURCE_TAG} 克隆失败：{message}")
        await asyncio.to_thread(_drop_dir, _STAGING_DIR)
        return _SyncOutcome(success=False, changed=False)

    await asyncio.to_thread(_drop_dir, RESOURCE_DIR)
    await asyncio.to_thread(_STAGING_DIR.rename, RESOURCE_DIR)
    logger.success(f"{_RESOURCE_TAG} 首次克隆完成")
    return _SyncOutcome(success=True, changed=True)


async def _collect_garbage() -> None:
    retcode, _, stderr = await run_git(RESOURCE_DIR, "gc", "--prune=now", timeout=GIT_CLONE_TIMEOUT)
    if retcode != 0:
        logger.warning(f"{_RESOURCE_TAG} 清理旧对象失败：{stderr}")


async def _update_from(branch: str) -> _SyncOutcome:
    current_remote = await git_get_remote_url(RESOURCE_DIR)
    if current_remote != RESOURCE_REPO_URL:
        success, message = await git_set_remote_url(RESOURCE_DIR, RESOURCE_REPO_URL)
        if not success:
            logger.warning(f"{_RESOURCE_TAG} 切换 origin 失败：{message}")

    old_head = await git_get_current_commit(RESOURCE_DIR)
    retcode, stdout, stderr = await run_git(
        RESOURCE_DIR,
        "fetch",
        "--depth=1",
        "--no-tags",
        "--",
        RESOURCE_REPO_URL,
        branch,
        timeout=GIT_CLONE_TIMEOUT,
    )
    if retcode != 0:
        logger.warning(f"{_RESOURCE_TAG} 拉取失败：{stderr or stdout}")
        return _SyncOutcome(success=False, changed=False)

    success, message = await git_reset_hard(RESOURCE_DIR, "FETCH_HEAD")
    if not success:
        logger.warning(f"{_RESOURCE_TAG} 更新失败：{message}")
        return _SyncOutcome(success=False, changed=False)

    new_head = await git_get_current_commit(RESOURCE_DIR)
    if not new_head:
        logger.warning(f"{_RESOURCE_TAG} 无法读取资源仓库版本")
        return _SyncOutcome(success=False, changed=False)
    changed = old_head != new_head
    if not changed:
        logger.info(f"{_RESOURCE_TAG} 资源已是最新")
    else:
        logger.success(f"{_RESOURCE_TAG} 资源更新完成")
    await _collect_garbage()
    return _SyncOutcome(success=True, changed=changed)


async def _sync_branch(branch: str) -> _SyncOutcome:
    if not _is_git_repo() or await asyncio.to_thread(_STAGING_DIR.exists):
        return await _clone_from(branch)
    return await _update_from(branch)


async def update_resources() -> bool:
    synced_changed = False
    async with _update_lock:
        await asyncio.to_thread(RESOURCE_DIR.mkdir, parents=True, exist_ok=True)
        branch = await _resolve_default_branch()
        if branch is None:
            return False

        outcome = await _sync_branch(branch)
        if not outcome.success:
            return False
        synced_changed = outcome.changed

    if synced_changed:
        reload_maps_data()
        # 延迟导入以避免插件顶层初始化阶段抢跑加载 calabiyau_ai
        from ...calabiyau_ai.knowledge.aliases import register_calabiyau_aliases
        from ...calabiyau_ai.knowledge.entities import sync_calabiyau_knowledge

        register_calabiyau_aliases()
        await sync_calabiyau_knowledge()
    return True


@on_core_start(priority=100)
async def sync_resources_on_start() -> None:
    """启动后同步资源；网络或 git 异常不阻断 Core。"""
    try:
        success = await update_resources()
    except OSError as exc:
        logger.warning(f"{_RESOURCE_TAG} git 不可用：{exc}")
        return
    if not success:
        logger.warning(f"{_RESOURCE_TAG} 启动同步失败，将继续使用本地已有资源")
