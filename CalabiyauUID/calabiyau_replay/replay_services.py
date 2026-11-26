"""对局回放下载、缓存复用与发送消息构造。"""

from pathlib import Path

from gsuid_core.pool import to_thread
from gsuid_core.models import Message
from gsuid_core.segment import MessageSegment

from ..calabiyau_config import CalabiyauConfig
from ..utils.api.dakanu import (
    DakanuError,
    is_valid_room_id,
    fetch_replay_download_ticket,
)
from ..utils.downloader import download_replay, find_cached_replay
from ..utils.utils.cache import KeyedLockPool

_room_locks: KeyedLockPool[str] = KeyedLockPool()


def parse_room_id(raw_text: str) -> str | None:
    """提取并校验对局 ID，非法时返回 None。"""
    cleaned = raw_text.strip()
    if not is_valid_room_id(cleaned):
        return None
    return cleaned


def _format_download_error(room_id: str, status_code: int | None) -> str:
    if status_code == 429:
        return "回放下载过于频繁，请稍后再试。"
    if status_code == 404:
        return f"没有找到对局 {room_id} 的回放文件，或下载链接已过期。"
    if status_code in {502, 503, 504}:
        return "战绩站暂时无法下载回放，请稍后再试。"
    return "下载对局回放失败，请稍后再试。"


async def get_cached_replay(room_id: str) -> Path | None:
    """在线程池中检查本地回放缓存。"""
    return await to_thread(find_cached_replay)(room_id)


async def ensure_replay_file(room_id: str) -> Path:
    """优先复用本地缓存，缺失时向 Dakanu 下载回放文件。"""
    async with _room_locks.acquire(room_id):
        cached = await get_cached_replay(room_id)
        if cached is not None:
            return cached
        ticket = await fetch_replay_download_ticket(room_id)
        result = await download_replay(room_id, ticket.download_url, ticket.cookies)
        if result.path is not None:
            return result.path
        raise DakanuError(_format_download_error(room_id, result.status_code))


async def build_replay_file_message(replay_path: Path) -> Message:
    """按配置构造 file:// 直指或 base64 文件消息段。"""
    if CalabiyauConfig.get_config("ReplayUseFileURI").data:
        file_uri = replay_path.resolve().as_uri()
        return Message(type="file", data=f"{replay_path.name}|{file_uri}")
    return await to_thread(MessageSegment.file)(replay_path, replay_path.name)
