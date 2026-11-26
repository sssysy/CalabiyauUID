"""玩家活跃趋势与世界频道动态数据拉取、素材解析与卡片渲染。"""

import asyncio
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

from gsuid_core.pool import to_thread
from gsuid_core.logger import logger

from ..utils.api.dakanu import (
    DakanuError,
    DakanuChatMessage,
    DakanuGameActivity,
    DakanuChatAggregate,
    role_image_url,
    avatar_image_url,
    fetch_meta_roles,
    fetch_game_activity,
    chat_emote_image_url,
    fetch_chat_aggregate,
)
from ..utils.downloader import resolve_image
from ..utils.helper.maps import get_role_display_names
from ..utils.utils.cache import AsyncTtlCache
from ..utils.helper.assets import (
    image_data_uri,
    local_role_image,
    local_avatar_image,
    local_chat_emote_image,
)
from ..utils.helper.ai_bridge import emit_ai_text
from ..utils.render.html.renderer.activity_card import render_activity_card
from ..utils.render.html.renderer.world_chat_card import (
    DEFAULT_WORLD_CHAT_LIMIT,
    WorldChatAssets,
    collect_chat_asset_ids,
    render_world_chat_card,
    select_recent_messages,
)

_CACHE_TTL_SECONDS = 60.0
_DOWNLOAD_CONCURRENCY = 8


@dataclass(frozen=True)
class _CardCache:
    image: bytes
    summary: str


_activity_card_cache: AsyncTtlCache[str, _CardCache] = AsyncTtlCache(
    maxsize=16,
    ttl_seconds=_CACHE_TTL_SECONDS,
)
_chat_card_cache: AsyncTtlCache[int, _CardCache] = AsyncTtlCache(
    maxsize=16,
    ttl_seconds=_CACHE_TTL_SECONDS,
)


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
        *(_resolve_image_uri(role_image_url(role_id), local_role_image(role_id), semaphore) for role_id in ordered)
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


def _format_activity_ai_summary(activity: DakanuGameActivity) -> str:
    est_points = activity["estimate"]["points"]
    last_est = est_points[-1] if est_points else None
    daily_text = f"{last_est['daily']:,}" if last_est is not None else "未知"
    active30_text = f"{last_est['active30d']:,}" if last_est is not None else "未知"
    pts = activity["points"]
    if not pts:
        return (
            f"【卡拉彼丘玩家活跃趋势（{activity['range']} / {activity['region'].upper() or 'CN'}）】\n"
            f"日活估算：{daily_text} | 30日活跃：{active30_text}\n暂无时序趋势数据。"
        )
    indices = [float(pt["index"]) for pt in pts]
    latest_pt = pts[-1]
    max_pt = max(pts, key=lambda pt: pt["index"])
    min_pt = min(pts, key=lambda pt: pt["index"])
    latest_time = datetime.fromtimestamp(latest_pt["at"]).strftime("%m-%d %H:%M")
    max_time = datetime.fromtimestamp(max_pt["at"]).strftime("%m-%d %H:%M")
    min_time = datetime.fromtimestamp(min_pt["at"]).strftime("%m-%d %H:%M")
    avg_val = sum(indices) / len(indices)
    return (
        f"【卡拉彼丘玩家活跃趋势（{activity['range']} / {activity['region'].upper() or 'CN'}）】\n"
        f"日活估算：{daily_text} | 30日活跃：{active30_text}\n"
        f"最新活跃指数：{latest_pt['index']:.1f}（{latest_time}）| 均值：{avg_val:.1f} | "
        f"峰值：{max_pt['index']:.1f}（{max_time}）| 谷值：{min_pt['index']:.1f}（{min_time}）"
    )


def _format_world_chat_ai_summary(aggregate: DakanuChatAggregate, recent_msgs: list[DakanuChatMessage]) -> str:
    scope = aggregate["scope"]
    lines: list[str] = [
        f"【卡拉彼丘世界频道动态（活跃频道 {scope['active_channels']}/{scope['channel_count']}，展示最近 {len(recent_msgs)} 条）】"
    ]
    for msg in recent_msgs[:12]:
        sent_time = datetime.fromtimestamp(msg["sent_at"]).strftime("%H:%M")
        lines.append(f"[{sent_time} #{msg['channel']}频道] {msg['nick']}：{msg['message']}")
    return "\n".join(lines)


async def build_activity_card(
    range_key: str = "24h",
    *,
    use_cache: bool = True,
) -> bytes:
    """拉取玩家活跃趋势并渲染卡片，带 60 秒内存缓存。"""

    async def _load() -> _CardCache:
        activity = await fetch_game_activity(range_key)
        summary = _format_activity_ai_summary(activity)
        image = await render_activity_card(activity)
        return _CardCache(image=image, summary=summary)

    cached = await _activity_card_cache.get_or_load(range_key, _load, use_cache=use_cache)
    emit_ai_text(cached.summary)
    return cached.image


async def build_world_chat_card(
    *,
    limit: int = DEFAULT_WORLD_CHAT_LIMIT,
    use_cache: bool = True,
) -> bytes:
    """拉取世界频道聚合动态并渲染卡片，带 60 秒内存缓存。"""

    async def _load() -> _CardCache:
        aggregate = await fetch_chat_aggregate(limit_per_channel=30)
        recent_msgs = select_recent_messages(aggregate["messages"], limit=limit)
        summary = _format_world_chat_ai_summary(aggregate, recent_msgs)
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
        return _CardCache(image=image, summary=summary)

    cached = await _chat_card_cache.get_or_load(limit, _load, use_cache=use_cache)
    emit_ai_text(cached.summary)
    return cached.image
