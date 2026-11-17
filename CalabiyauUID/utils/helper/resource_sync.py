"""启动后从镜像同步资源仓库。"""

import os
import re
import json
import stat
import time
import shutil
import asyncio
from typing import TypedDict
from pathlib import Path
from dataclasses import dataclass
from collections.abc import Callable

import httpx

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

from ..utils.paths import RESOURCE_DIR

MIRROR_MANIFEST_URL = "https://klbq.sssysy.top/resource_mirror.json"
_MIRROR_TAG = "[卡拉彼丘·资源镜像]"
_RESOURCE_TAG = "[卡拉彼丘·资源更新]"
_PROBE_TIMEOUT = 5
_MANIFEST_TIMEOUT = 10
_STAGING_DIR = RESOURCE_DIR.with_name(f"{RESOURCE_DIR.name}-staging")
_update_lock = asyncio.Lock()


class ResourceMirror(TypedDict):
    name: str
    url: str
    priority: int


@dataclass(frozen=True)
class MirrorProbe:
    mirror: ResourceMirror
    branch: str
    latency_ms: int


@dataclass(frozen=True)
class _SyncOutcome:
    success: bool
    changed: bool


def _as_str_map(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result


def _as_object_list(value: object) -> list[object] | None:
    if not isinstance(value, list):
        return None
    return [item for item in value]


def _parse_mirror(value: object) -> ResourceMirror | None:
    data = _as_str_map(value)
    if data is None:
        return None
    if "name" not in data or "url" not in data or "priority" not in data:
        return None
    name = data["name"]
    url = data["url"]
    priority = data["priority"]
    if not isinstance(name, str) or not isinstance(url, str):
        return None
    if not name or not url.startswith(("https://", "http://")):
        return None
    if isinstance(priority, bool) or not isinstance(priority, int):
        return None
    return ResourceMirror(name=name, url=url, priority=priority)


def _parse_manifest(payload: object) -> list[ResourceMirror] | None:
    data = _as_str_map(payload)
    if data is None:
        return None
    if "version" not in data or "mirrors" not in data:
        return None
    if data["version"] != 1:
        return None
    raw_mirrors = _as_object_list(data["mirrors"])
    if raw_mirrors is None or not raw_mirrors:
        return None
    mirrors: list[ResourceMirror] = []
    for raw in raw_mirrors:
        mirror = _parse_mirror(raw)
        if mirror is None:
            logger.warning(f"{_MIRROR_TAG} 镜像条目格式不正确，已跳过")
            continue
        mirrors.append(mirror)
    return mirrors or None


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


async def _load_mirrors() -> list[ResourceMirror] | None:
    try:
        async with httpx.AsyncClient(timeout=_MANIFEST_TIMEOUT) as client:
            response = await client.get(MIRROR_MANIFEST_URL)
    except httpx.HTTPError as exc:
        logger.warning(f"{_MIRROR_TAG} 读取镜像清单失败：{exc}")
        return None
    if response.status_code != 200:
        logger.warning(f"{_MIRROR_TAG} 读取镜像清单失败：HTTP {response.status_code}")
        return None

    try:
        payload: object = json.loads(response.content)
    except json.JSONDecodeError as exc:
        logger.warning(f"{_MIRROR_TAG} 镜像清单不是合法 JSON：{exc}")
        return None
    mirrors = _parse_manifest(payload)
    if mirrors is None:
        logger.warning(f"{_MIRROR_TAG} 镜像清单内容不合法")
        return None
    logger.info(f"{_MIRROR_TAG} 从 {MIRROR_MANIFEST_URL} 获取到 {len(mirrors)} 个镜像，开始逐一尝试")
    return mirrors


async def _probe_mirror(mirror: ResourceMirror) -> MirrorProbe | None:
    started = time.monotonic()
    retcode, stdout, stderr = await run_git(
        RESOURCE_DIR,
        "ls-remote",
        "--symref",
        mirror["url"],
        "HEAD",
        timeout=_PROBE_TIMEOUT,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if retcode != 0:
        logger.warning(f"{_MIRROR_TAG} 镜像 {mirror['name']} 探测失败：{stderr or 'timeout'}")
        return None
    branch = _parse_default_branch(stdout)
    if branch is None:
        logger.warning(f"{_MIRROR_TAG} 镜像 {mirror['name']} 未返回默认分支")
        return None
    logger.info(f"{_MIRROR_TAG} 镜像 {mirror['name']} 延迟 {elapsed_ms}ms，分支 {branch}")
    return MirrorProbe(mirror=mirror, branch=branch, latency_ms=elapsed_ms)


async def _clone_from(probe: MirrorProbe) -> _SyncOutcome:
    # 目录已有旧素材但不是 git 仓库时，git clone 会拒绝写入非空目录
    await asyncio.to_thread(_drop_dir, _STAGING_DIR)
    success, message = await git_clone(
        probe.mirror["url"],
        _STAGING_DIR,
        branch=probe.branch,
        depth=1,
        timeout=GIT_CLONE_TIMEOUT,
    )
    if not success:
        logger.warning(f"{_MIRROR_TAG} 从 {probe.mirror['name']} 克隆失败：{message}")
        await asyncio.to_thread(_drop_dir, _STAGING_DIR)
        return _SyncOutcome(success=False, changed=False)

    await asyncio.to_thread(_drop_dir, RESOURCE_DIR)
    await asyncio.to_thread(_STAGING_DIR.rename, RESOURCE_DIR)
    logger.success(f"{_RESOURCE_TAG} 首次克隆完成，来源 {probe.mirror['name']}")
    return _SyncOutcome(success=True, changed=True)


async def _collect_garbage() -> None:
    retcode, _, stderr = await run_git(RESOURCE_DIR, "gc", "--prune=now", timeout=GIT_CLONE_TIMEOUT)
    if retcode != 0:
        logger.warning(f"{_RESOURCE_TAG} 清理旧对象失败：{stderr}")


async def _update_from(probe: MirrorProbe) -> _SyncOutcome:
    current_remote = await git_get_remote_url(RESOURCE_DIR)
    if current_remote != probe.mirror["url"]:
        success, message = await git_set_remote_url(RESOURCE_DIR, probe.mirror["url"])
        if not success:
            logger.warning(f"{_MIRROR_TAG} 切换 origin 失败：{message}")

    old_head = await git_get_current_commit(RESOURCE_DIR)
    retcode, stdout, stderr = await run_git(
        RESOURCE_DIR,
        "fetch",
        "--depth=1",
        "--no-tags",
        "--",
        probe.mirror["url"],
        probe.branch,
        timeout=GIT_CLONE_TIMEOUT,
    )
    if retcode != 0:
        logger.warning(f"{_MIRROR_TAG} 从 {probe.mirror['name']} 拉取失败：{stderr or stdout}")
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
        logger.success(f"{_RESOURCE_TAG} 资源更新完成，来源 {probe.mirror['name']}")
    await _collect_garbage()
    return _SyncOutcome(success=True, changed=changed)


async def _sync_with(probe: MirrorProbe) -> _SyncOutcome:
    if not _is_git_repo() or await asyncio.to_thread(_STAGING_DIR.exists):
        return await _clone_from(probe)
    return await _update_from(probe)


async def update_resources() -> bool:
    synced = False
    synced_changed = False
    async with _update_lock:
        await asyncio.to_thread(RESOURCE_DIR.mkdir, parents=True, exist_ok=True)
        mirrors = await _load_mirrors()
        if mirrors is None:
            return False

        probes = await asyncio.gather(*(_probe_mirror(mirror) for mirror in mirrors))
        available = sorted(
            (probe for probe in probes if probe is not None),
            key=lambda probe: (probe.latency_ms, probe.mirror["priority"]),
        )
        if not available:
            logger.warning(f"{_MIRROR_TAG} 所有镜像均不可用")
            return False

        for probe in available:
            outcome = await _sync_with(probe)
            if outcome.success:
                synced = True
                synced_changed = outcome.changed
                break
        if not synced:
            logger.warning(f"{_RESOURCE_TAG} 所有镜像同步失败")
            return False

    if synced_changed:
        # 延迟导入以避免插件顶层初始化阶段抢跑加载 calabiyau_ai
        from ...calabiyau_ai.knowledge.entities import sync_calabiyau_knowledge

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
