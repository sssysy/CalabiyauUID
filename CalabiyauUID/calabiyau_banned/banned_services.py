"""封神榜数据拉取、头像资源加载与卡片构建服务。"""

import time
import asyncio
from pathlib import Path
from dataclasses import dataclass

from gsuid_core.pool import to_thread

from ..utils.api.dakanu import (
    DakanuError,
    DakanuBannedEntry,
    tier_image_url,
    avatar_image_url,
    fetch_banned_players,
)
from ..utils.downloader import resolve_image
from ..utils.helper.assets import image_data_uri, local_tier_image, local_avatar_image
from ..utils.helper.ai_bridge import emit_ai_text
from ..utils.helper.player_resolve import is_numeric_uid
from ..utils.render.html.renderer.banned_card import BannedSearchMode, render_banned_card
from ..utils.render.html.renderer.summary_card import tier_display

_DEFAULT_LIMIT = 21
_CACHE_TTL_SECONDS = 30.0
_DOWNLOAD_CONCURRENCY = 8


@dataclass(frozen=True)
class _BannedCardCache:
    expires_at: float
    image: bytes
    summary: str


_default_cache_lock = asyncio.Lock()
_default_card_cache: _BannedCardCache | None = None


def _read_image_uri(path: Path) -> str:
    return image_data_uri(path.read_bytes(), path.suffix)


async def _resolve_avatar_uri(avatar_id: int, semaphore: asyncio.Semaphore) -> str:
    local_path = local_avatar_image(avatar_id)
    if local_path is not None and local_path.is_file() and local_path.stat().st_size > 0:
        return await to_thread(_read_image_uri)(local_path)
    async with semaphore:
        path = await resolve_image(avatar_image_url(avatar_id), local_path)
    if path is None:
        return ""
    return await to_thread(_read_image_uri)(path)


async def _resolve_tier_uri(tier_index: int, semaphore: asyncio.Semaphore) -> str:
    local_path = local_tier_image(tier_index)
    if local_path is not None and local_path.is_file() and local_path.stat().st_size > 0:
        return await to_thread(_read_image_uri)(local_path)
    url = tier_image_url(tier_index)
    if not url:
        return ""
    async with semaphore:
        path = await resolve_image(url, local_path)
    if path is None:
        return ""
    return await to_thread(_read_image_uri)(path)


async def _load_avatar_images(
    entries: list[DakanuBannedEntry],
    semaphore: asyncio.Semaphore,
) -> dict[int, str]:
    avatar_ids = sorted({entry["avatarId"] for entry in entries if entry["avatarId"] is not None and entry["avatarId"] > 0})
    if not avatar_ids:
        return {}
    uris = await asyncio.gather(*(_resolve_avatar_uri(avatar_id, semaphore) for avatar_id in avatar_ids))
    return {avatar_id: uri for avatar_id, uri in zip(avatar_ids, uris, strict=True)}


async def _load_tier_images(
    entries: list[DakanuBannedEntry],
    semaphore: asyncio.Semaphore,
) -> dict[int, str]:
    tier_indices = sorted(
        {
            tier_display(entry["segment"])[2]
            for entry in entries
            if entry["segment"] is not None and entry["segment"] > 0
        }
        - {0}
    )
    if not tier_indices:
        return {}
    uris = await asyncio.gather(*(_resolve_tier_uri(tier_idx, semaphore) for tier_idx in tier_indices))
    return {tier_idx: uri for tier_idx, uri in zip(tier_indices, uris, strict=True)}


async def _render_entries(
    entries: list[DakanuBannedEntry],
    total: int,
    *,
    search_mode: BannedSearchMode,
) -> bytes:
    emit_ai_text(_format_banned_ai_summary(entries, total, search_mode=search_mode))
    semaphore = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)
    avatar_images, tier_images = await asyncio.gather(
        _load_avatar_images(entries, semaphore),
        _load_tier_images(entries, semaphore),
    )
    return await render_banned_card(
        entries,
        total,
        avatar_images,
        tier_images,
        search_mode=search_mode,
        page=1,
        page_size=_DEFAULT_LIMIT,
    )


def _format_banned_ai_summary(
    entries: list[DakanuBannedEntry],
    total: int,
    *,
    search_mode: BannedSearchMode,
) -> str:
    mode_label = {"list": "最新封禁榜", "exact": "UID 精确查询", "fuzzy": "昵称查询"}[search_mode]
    lines: list[str] = [f"【卡拉彼丘封神榜（{mode_label}，匹配总计 {total} 条，展示 {len(entries)} 条）】"]
    for idx, entry in enumerate(entries[:10], start=1):
        uid_text = entry["playerId"] if entry["playerId"] is not None else entry["maskedId"]
        tier_text = tier_display(entry["segment"])[0] if entry["segment"] is not None else "未知段位"
        lines.append(
            f"{idx}. {entry['nickname']}（UID:{uid_text}，{tier_text}，对局数 {entry['matchCount']}）"
            f"｜公告：{entry['announcementTitle']}"
        )
    return "\n".join(lines)


async def build_banned_card(*, query: str = "", use_cache: bool = True) -> bytes:
    """拉取封神榜前 21 条或按昵称/UID 查询并渲染封神榜卡片。"""
    global _default_card_cache
    cleaned = query.strip()
    if not cleaned:
        async with _default_cache_lock:
            now = time.monotonic()
            if use_cache and _default_card_cache is not None and now < _default_card_cache.expires_at:
                emit_ai_text(_default_card_cache.summary)
                return _default_card_cache.image
            response = await fetch_banned_players(offset=0, limit=_DEFAULT_LIMIT)
            summary = _format_banned_ai_summary(response["entries"], response["total"], search_mode="list")
            image = await _render_entries(response["entries"], response["total"], search_mode="list")
            _default_card_cache = _BannedCardCache(
                expires_at=time.monotonic() + _CACHE_TTL_SECONDS,
                image=image,
                summary=summary,
            )
            return image

    response = await fetch_banned_players(offset=0, limit=_DEFAULT_LIMIT, query=cleaned)
    entries = response["entries"]
    total = response["total"]
    if is_numeric_uid(cleaned):
        entries = [entry for entry in entries if entry["playerId"] == cleaned]
        if not entries:
            raise DakanuError(f"未查询到 UID {cleaned} 的封禁记录。")
        return await _render_entries(entries, len(entries), search_mode="exact")

    if not entries:
        raise DakanuError(f"未查询到昵称包含「{cleaned}」的封禁记录。")
    return await _render_entries(entries, total, search_mode="fuzzy")
