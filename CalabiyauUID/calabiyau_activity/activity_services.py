"""卡拉彼丘进行中活动的数据拉取、封面缓存与时间轴卡片渲染。"""

import asyncio
from pathlib import Path
from dataclasses import dataclass

from ..utils.downloader import resolve_image
from ..utils.utils.cache import AsyncTtlCache
from ..utils.helper.assets import (
    local_card_bg_image,
    read_image_data_uri,
)
from ..utils.helper.ai_bridge import emit_ai_text
from ..utils.api.biligame_wiki import (
    WikiActivityItem,
    beijing_now,
    fetch_ongoing_activities,
)
from ..utils.helper.activity_remind import sync_reminders_from_activities
from ..utils.render.html.renderer.activity_timeline_card import render_activity_timeline_card

_CACHE_TTL_SECONDS = 300.0
_DOWNLOAD_CONCURRENCY = 6


@dataclass(frozen=True)
class _CardCache:
    image: bytes
    summary: str


_timeline_card_cache: AsyncTtlCache[str, _CardCache] = AsyncTtlCache(
    maxsize=1,
    ttl_seconds=_CACHE_TTL_SECONDS,
)


async def _resolve_image_uri(
    url: str,
    local_path: Path | None,
    semaphore: asyncio.Semaphore,
) -> str:
    cached = await read_image_data_uri(local_path)
    if cached:
        return cached
    if not url:
        return ""
    async with semaphore:
        path = await resolve_image(url, local_path)
    return await read_image_data_uri(path)


async def _load_activity_images(
    activities: list[WikiActivityItem],
    semaphore: asyncio.Semaphore,
) -> dict[str, str]:
    url_by_name: dict[str, str] = {}
    for item in activities:
        if item.image_name and item.image_url and item.image_name not in url_by_name:
            url_by_name[item.image_name] = item.image_url
    ordered_names = list(url_by_name.keys())
    uris = await asyncio.gather(*(_resolve_image_uri(url_by_name[name], None, semaphore) for name in ordered_names))
    return {name: uri for name, uri in zip(ordered_names, uris, strict=True)}


def _format_activity_timeline_ai_summary(activities: list[WikiActivityItem]) -> str:
    if not activities:
        return "【卡拉彼丘进行中活动】当前暂无进行中的活动。"
    lines: list[str] = [f"【卡拉彼丘当前进行中活动（共 {len(activities)} 项）】"]
    for idx, item in enumerate(activities, start=1):
        start_text = item.start_at.strftime("%Y-%m-%d %H:%M")
        end_text = "常驻" if item.is_permanent else item.end_at.strftime("%Y-%m-%d %H:%M")
        summary_note = f"｜{item.summary}" if item.summary else ""
        lines.append(f"{idx}. {item.title}（{start_text} ~ {end_text}）{summary_note}")
    return "\n".join(lines)


async def build_event_timeline_card(*, use_cache: bool = True) -> bytes:
    """获取当前进行中活动并渲染时间轴卡片，带 5 分钟内存缓存。"""

    async def _load() -> _CardCache:
        now = beijing_now()
        activities = await fetch_ongoing_activities(now)
        summary = _format_activity_timeline_ai_summary(activities)
        await sync_reminders_from_activities(activities, now, allow_catchup_send=False)
        semaphore = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)
        banner_path = local_card_bg_image()
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
        return _CardCache(image=image, summary=summary)

    cached = await _timeline_card_cache.get_or_load("timeline", _load, use_cache=use_cache)
    emit_ai_text(cached.summary)
    return cached.image
