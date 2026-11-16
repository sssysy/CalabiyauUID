"""玩家活跃趋势与世界频道动态数据拉取、素材解析与卡片渲染。"""

import time
import asyncio
from pathlib import Path
from dataclasses import dataclass

from gsuid_core.pool import to_thread
from gsuid_core.logger import logger

from ..utils.api.dakanu import (
    DakanuError,
    role_image_url,
    avatar_image_url,
    fetch_meta_roles,
    fetch_game_activity,
    chat_emote_image_url,
    fetch_chat_aggregate,
)
from ..utils.downloader import resolve_image
from ..utils.helper.maps import get_role_display_names
from ..utils.helper.assets import (
    image_data_uri,
    local_role_image,
    local_avatar_image,
    local_chat_emote_image,
)
from ..utils.render.html.activity_card import render_activity_card
from ..utils.render.html.world_chat_card import (
    DEFAULT_WORLD_CHAT_LIMIT,
    WorldChatAssets,
    collect_chat_asset_ids,
    select_recent_messages,
    render_world_chat_card,
)

_CACHE_TTL_SECONDS = 60.0
_DOWNLOAD_CONCURRENCY = 8


@dataclass(frozen=True)
class _CardCache:
    expires_at: float
    image: bytes


_activity_cache_lock = asyncio.Lock()
_activity_cached_cards: dict[str, _CardCache] = {}

_chat_cache_lock = asyncio.Lock()
_chat_cached_cards: dict[int, _CardCache] = {}


def _read_image_uri(path: Path) -> str:
    return image_data_uri(path.read_bytes(), path.suffix)


async def _resolve_image_uri(
    url: str,
    local_path: Path | None,
    semaphore: asyncio.Semaphore,
) -> str:
    if local_path is not None and local_path.is_file() and local_path.stat().st_size > 0:
        return await to_thread(_read_image_uri)(local_path)
    if not url:
        return ""
    async with semaphore:
        path = await resolve_image(url, local_path)
    if path is None:
        return ""
    return await to_thread(_read_image_uri)(path)


async def _load_avatar_images(
    avatar_ids: set[int],
    semaphore: asyncio.Semaphore,
) -> dict[int, str]:
    ordered = sorted(avatar_ids)
    uris = await asyncio.gather(
        *(
            _resolve_image_uri(avatar_image_url(avatar_id), local_avatar_image(avatar_id), semaphore)
            for avatar_id in ordered
        )
    )
    return {avatar_id: uri for avatar_id, uri in zip(ordered, uris, strict=True)}


async def _load_role_images(
    role_ids: set[int],
    semaphore: asyncio.Semaphore,
) -> dict[int, str]:
    ordered = sorted(role_ids)
    uris = await asyncio.gather(
        *(
            _resolve_image_uri(role_image_url(role_id), local_role_image(role_id), semaphore)
            for role_id in ordered
        )
    )
    return {role_id: uri for role_id, uri in zip(ordered, uris, strict=True)}


async def _load_emote_images(
    emote_ids: set[str],
    semaphore: asyncio.Semaphore,
) -> dict[str, str]:
    ordered = sorted(emote_ids)
    uris = await asyncio.gather(
        *(
            _resolve_image_uri(
                chat_emote_image_url(emote_id),
                local_chat_emote_image(emote_id),
                semaphore,
            )
            for emote_id in ordered
        )
    )
    return {emote_id: uri for emote_id, uri in zip(ordered, uris, strict=True)}


async def _load_role_names(role_ids: set[int]) -> dict[int, str]:
    local_names = get_role_display_names()
    if not role_ids or all(role_id in local_names for role_id in role_ids):
        return local_names
    try:
        remote_roles = await fetch_meta_roles()
    except DakanuError as exc:
        logger.warning(f"[卡拉彼丘·世界聊天] 读取角色名称字典失败：{exc}")
        return local_names
    return {**remote_roles, **local_names}


async def build_activity_card(
    range_key: str = "24h",
    *,
    use_cache: bool = True,
) -> bytes:
    """拉取玩家活跃趋势并渲染卡片，带 60 秒内存缓存。"""
    async with _activity_cache_lock:
        now = time.monotonic()
        if (
            use_cache
            and range_key in _activity_cached_cards
            and now < _activity_cached_cards[range_key].expires_at
        ):
            return _activity_cached_cards[range_key].image

        activity = await fetch_game_activity(range_key)
        image = await render_activity_card(activity)
        _activity_cached_cards[range_key] = _CardCache(
            expires_at=time.monotonic() + _CACHE_TTL_SECONDS,
            image=image,
        )
        return image


async def build_world_chat_card(
    *,
    limit: int = DEFAULT_WORLD_CHAT_LIMIT,
    use_cache: bool = True,
) -> bytes:
    """拉取世界频道聚合动态并渲染卡片，带 60 秒内存缓存。"""
    async with _chat_cache_lock:
        now = time.monotonic()
        if (
            use_cache
            and limit in _chat_cached_cards
            and now < _chat_cached_cards[limit].expires_at
        ):
            return _chat_cached_cards[limit].image

        aggregate = await fetch_chat_aggregate(limit_per_channel=30)
        recent_msgs = select_recent_messages(aggregate["messages"], limit=limit)
        avatar_ids, role_ids, emote_ids = collect_chat_asset_ids(recent_msgs)

        semaphore = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)
        avatar_images, role_images, emote_images, role_names = await asyncio.gather(
            _load_avatar_images(avatar_ids, semaphore),
            _load_role_images(role_ids, semaphore),
            _load_emote_images(emote_ids, semaphore),
            _load_role_names(role_ids),
        )
        assets = WorldChatAssets(
            avatar_images=avatar_images,
            role_images=role_images,
            emote_images=emote_images,
            role_names=role_names,
        )
        image = await render_world_chat_card(aggregate, assets, limit=limit)
        _chat_cached_cards[limit] = _CardCache(
            expires_at=time.monotonic() + _CACHE_TTL_SECONDS,
            image=image,
        )
        return image
