"""卡拉彼丘进行中活动的数据拉取、封面缓存与时间轴卡片渲染。"""

import time
import asyncio
from pathlib import Path
from dataclasses import dataclass

from gsuid_core.pool import to_thread

from ..utils.downloader import resolve_image
from ..utils.helper.assets import (
    image_data_uri,
    local_banner_bg_image,
)
from ..utils.api.biligame_wiki import (
    WikiActivityItem,
    beijing_now,
    fetch_ongoing_activities,
)
from ..utils.render.html.activity_timeline_card import render_activity_timeline_card

_CACHE_TTL_SECONDS = 300.0
_DOWNLOAD_CONCURRENCY = 6


@dataclass(frozen=True)
class _CardCache:
    expires_at: float
    image: bytes


_timeline_cache_lock = asyncio.Lock()
_timeline_cached_card: _CardCache | None = None


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


async def _load_activity_images(
    activities: list[WikiActivityItem],
    semaphore: asyncio.Semaphore,
) -> dict[str, str]:
    url_by_name: dict[str, str] = {}
    for item in activities:
        if item.image_name and item.image_url and item.image_name not in url_by_name:
            url_by_name[item.image_name] = item.image_url
    ordered_names = list(url_by_name.keys())
    uris = await asyncio.gather(
        *(
            _resolve_image_uri(url_by_name[name], None, semaphore)
            for name in ordered_names
        )
    )
    return {name: uri for name, uri in zip(ordered_names, uris, strict=True)}


async def build_event_timeline_card(*, use_cache: bool = True) -> bytes:
    """获取当前进行中活动并渲染时间轴卡片，带 5 分钟内存缓存。"""
    global _timeline_cached_card
    async with _timeline_cache_lock:
        mono_now = time.monotonic()
        if (
            use_cache
            and _timeline_cached_card is not None
            and mono_now < _timeline_cached_card.expires_at
        ):
            return _timeline_cached_card.image

        now = beijing_now()
        activities = await fetch_ongoing_activities(now)
        semaphore = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)
        banner_path = local_banner_bg_image()
        banner_bg_uri, image_uris = await asyncio.gather(
            _resolve_image_uri("", banner_path, semaphore),
            _load_activity_images(activities, semaphore),
        )
        image = await render_activity_timeline_card(
            activities,
            image_uris,
            banner_bg_uri,
            now,
        )
        _timeline_cached_card = _CardCache(
            expires_at=time.monotonic() + _CACHE_TTL_SECONDS,
            image=image,
        )
        return image
