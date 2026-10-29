"""启动后同步资源文件，只补本地缺失文件。"""

import json
import asyncio
from pathlib import Path, PurePosixPath

import httpx

from gsuid_core.pool import to_thread
from gsuid_core.logger import logger
from gsuid_core.server import on_core_start

from ..utils.paths import DATA_DIR

RESOURCE_BASE_URL = "https://klbq.sssysy.top/"
_LIST_TIMEOUT = 30.0
_DOWNLOAD_TIMEOUT = 120.0
_DOWNLOAD_CONCURRENCY = 8
_IGNORED_NAMES = frozenset({".openlist"})


def parse_resource_keys(value: object) -> list[str]:
    """从资源列表 JSON 中提取可安全落盘的文件 key。"""
    if not isinstance(value, list):
        return []
    keys: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or item.endswith("/"):
            continue
        path = PurePosixPath(item)
        if path.is_absolute() or ".." in path.parts or "\\" in item:
            continue
        if path.name in _IGNORED_NAMES:
            continue
        keys.append(item)
    return sorted(set(keys))


def missing_resource_keys(keys: list[str], data_dir: Path) -> list[str]:
    """返回数据目录中不存在或为空的文件 key。"""
    missing: list[str] = []
    for key in keys:
        local = data_dir / PurePosixPath(key)
        if not local.is_file() or local.stat().st_size <= 0:
            missing.append(key)
    return missing


def _write_file(content: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".part")
    temporary.write_bytes(content)
    temporary.replace(target)


async def fetch_resource_keys(client: httpx.AsyncClient) -> list[str]:
    response = await client.get(RESOURCE_BASE_URL, timeout=_LIST_TIMEOUT)
    response.raise_for_status()
    return parse_resource_keys(response.json())


async def download_resource_file(client: httpx.AsyncClient, key: str, semaphore: asyncio.Semaphore) -> bool:
    target = DATA_DIR / PurePosixPath(key)
    url = RESOURCE_BASE_URL + key
    async with semaphore:
        logger.debug(f"[卡拉彼丘·资源下载] 开始下载：{url}")
        try:
            response = await client.get(url, timeout=_DOWNLOAD_TIMEOUT)
        except (httpx.HTTPError, OSError) as exc:
            logger.warning(f"[卡拉彼丘·资源下载] 下载失败 {key}：{exc}")
            return False
        if response.status_code != 200 or not response.content:
            logger.warning(f"[卡拉彼丘·资源下载] 下载失败 {key} HTTP {response.status_code}")
            return False
        expected = response.headers.get("content-length")
        if expected is not None and expected.isdigit() and int(expected) != len(response.content):
            logger.warning(f"[卡拉彼丘·资源下载] 下载内容不完整 {key}，将下次重试")
            return False
        try:
            await to_thread(_write_file)(response.content, target)
        except OSError as exc:
            logger.warning(f"[卡拉彼丘·资源下载] 写入失败 {key}：{exc}")
            return False
        logger.debug(f"[卡拉彼丘·资源下载] 下载完毕：{url}")
        return True


async def sync_missing_files(rounds: int = 2) -> tuple[int, int, int]:
    """返回（资源数、各轮缺失合计、下载成功合计）。"""
    total = 0
    missing_total = 0
    succeeded = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for index in range(rounds):
            keys = await fetch_resource_keys(client)
            total = len(keys)
            missing = missing_resource_keys(keys, DATA_DIR)
            logger.info(f"[卡拉彼丘·资源下载] 第 {index + 1} 轮：资源 {total} 项，本地缺失 {len(missing)} 项")
            if not missing:
                break
            missing_total += len(missing)
            semaphore = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)
            results = await asyncio.gather(*(download_resource_file(client, key, semaphore) for key in missing))
            succeeded += sum(1 for result in results if result)
    return total, missing_total, succeeded


@on_core_start(priority=100)
async def sync_resources_on_start() -> None:
    """启动后后台同步资源；网络异常不阻断 Core。"""
    try:
        total, missing, succeeded = await sync_missing_files()
    except (httpx.HTTPError, json.JSONDecodeError, RuntimeError, OSError) as exc:
        logger.warning(f"[卡拉彼丘·资源下载] 启动同步失败：{exc}")
        return
    logger.success("[卡拉彼丘·资源下载] 所有资源下载完毕")
