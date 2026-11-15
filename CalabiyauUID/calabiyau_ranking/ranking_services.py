"""排位段位榜数据拉取、素材解析与卡片渲染。"""

import time
import asyncio
from pathlib import Path
from dataclasses import dataclass

from gsuid_core.pool import to_thread

from ..utils.api.dakanu import (
    DakanuRankingFloor,
    DakanuRankingsBoard,
    fetch_rankings,
    role_image_url,
    tier_image_url,
    avatar_image_url,
    fetch_ranking_floor,
    fetch_current_season,
)
from ..utils.downloader import resolve_image
from ..utils.helper.assets import (
    image_data_uri,
    local_role_image,
    local_tier_image,
    local_avatar_image,
)
from ..utils.render.html.ranking_card import RankingCardAssets, render_ranking_card
from ..utils.render.html.summary_card import tier_index

_CACHE_TTL_SECONDS = 30.0
_DOWNLOAD_CONCURRENCY = 8


@dataclass(frozen=True)
class _RankingCardCache:
    expires_at: float
    image: bytes


_cache_lock = asyncio.Lock()
_cached_card: _RankingCardCache | None = None


def _read_image_uri(path: Path) -> str:
    return image_data_uri(path.read_bytes(), path.suffix)


async def _resolve_image_uri(url: str, local_path: Path | None, semaphore: asyncio.Semaphore) -> str:
    if local_path is not None and local_path.is_file() and local_path.stat().st_size > 0:
        return await to_thread(_read_image_uri)(local_path)
    if not url:
        return ""
    async with semaphore:
        path = await resolve_image(url, local_path)
    if path is None:
        return ""
    return await to_thread(_read_image_uri)(path)


async def _load_avatar_images(avatar_ids: set[int], semaphore: asyncio.Semaphore) -> dict[int, str]:
    ordered = sorted(avatar_ids)
    uris = await asyncio.gather(
        *(
            _resolve_image_uri(avatar_image_url(avatar_id), local_avatar_image(avatar_id), semaphore)
            for avatar_id in ordered
        )
    )
    return {avatar_id: uri for avatar_id, uri in zip(ordered, uris, strict=True)}


async def _load_role_images(role_ids: set[int], semaphore: asyncio.Semaphore) -> dict[int, str]:
    ordered = sorted(role_ids)
    uris = await asyncio.gather(
        *(_resolve_image_uri(role_image_url(role_id), local_role_image(role_id), semaphore) for role_id in ordered)
    )
    return {role_id: uri for role_id, uri in zip(ordered, uris, strict=True)}


async def _load_tier_images(tier_indices: set[int], semaphore: asyncio.Semaphore) -> dict[int, str]:
    ordered = sorted(tier_indices)
    uris = await asyncio.gather(
        *(_resolve_image_uri(tier_image_url(idx), local_tier_image(idx), semaphore) for idx in ordered)
    )
    return {idx: uri for idx, uri in zip(ordered, uris, strict=True)}


async def _build_assets(board: DakanuRankingsBoard) -> RankingCardAssets:
    avatar_ids: set[int] = set()
    role_ids: set[int] = set()
    tier_indices: set[int] = set()
    for entry in board["entries"]:
        avatar_ids.add(entry["avatarId"])
        for role_id in entry["roles"][:3]:
            role_ids.add(role_id)
        idx = tier_index(entry["segment"])
        if idx > 0:
            tier_indices.add(idx)

    semaphore = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)
    avatar_images, role_images, tier_images = await asyncio.gather(
        _load_avatar_images(avatar_ids, semaphore),
        _load_role_images(role_ids, semaphore),
        _load_tier_images(tier_indices, semaphore),
    )
    return RankingCardAssets(
        avatar_images=avatar_images,
        role_images=role_images,
        tier_images=tier_images,
    )


async def _fetch_ranking_bundle() -> tuple[DakanuRankingsBoard, DakanuRankingFloor | None, str]:
    board, floor, season = await asyncio.gather(
        fetch_rankings(rank_type=1, page=1, page_size=50),
        fetch_ranking_floor(season_id=0),
        fetch_current_season(),
    )
    season_label = season["ranked_season"]["label"] if season is not None else ""
    return board, floor, season_label


async def build_ranking_card(*, use_cache: bool = True) -> bytes:
    """拉取前 50 名排位段位榜并渲染卡片，带 30 秒短时内存缓存。"""
    global _cached_card
    async with _cache_lock:
        now = time.monotonic()
        if use_cache and _cached_card is not None and now < _cached_card.expires_at:
            return _cached_card.image

        board, floor, season_label = await _fetch_ranking_bundle()
        assets = await _build_assets(board)
        image = await render_ranking_card(board, floor, season_label, assets)
        _cached_card = _RankingCardCache(expires_at=time.monotonic() + _CACHE_TTL_SECONDS, image=image)
        return image
