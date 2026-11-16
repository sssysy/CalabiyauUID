"""排行榜数据拉取、角色解析、素材加载与卡片构建服务。"""

import time
import asyncio
from typing import Literal
from pathlib import Path
from dataclasses import dataclass

from gsuid_core.pool import to_thread
from gsuid_core.logger import logger

from ..utils.api.dakanu import (
    DakanuError,
    DakanuRankingFloor,
    DakanuRankingsBoard,
    fetch_rankings,
    role_image_url,
    tier_image_url,
    avatar_image_url,
    fetch_meta_roles,
    fetch_ranking_floor,
    fetch_roles_ranking,
    fetch_current_season,
    challenge_tier_image_url,
)
from ..utils.downloader import resolve_image
from ..utils.helper.maps import resolve_role_alias, get_role_display_names
from ..utils.helper.assets import (
    image_data_uri,
    local_role_image,
    local_tier_image,
    local_avatar_image,
    local_challenge_tier_image,
)
from ..utils.render.html.renderer.ranking_card import RankingCardAssets, render_ranking_card
from ..utils.render.html.renderer.summary_card import tier_index, challenge_tier_index
from ..utils.render.html.renderer.roles_ranking_card import render_roles_ranking_card

_CACHE_TTL_SECONDS = 30.0
_DOWNLOAD_CONCURRENCY = 8
_ROLE_USAGE_PREFIX = "请提供角色名或角色 ID，例如：kq超弦体排行 星绘 或 kq超弦体排行 146"

RolesSortBy = Literal["winRate", "appearanceRate"]
TierMode = Literal["ranked", "challenge", "none"]


@dataclass(frozen=True)
class _RankingCardCache:
    expires_at: float
    image: bytes


_board_cache_lock = asyncio.Lock()
_cached_board_cards: dict[tuple[int, int | None], _RankingCardCache] = {}
_roles_cache_lock = asyncio.Lock()
_cached_roles_cards: dict[tuple[RolesSortBy, bool], _RankingCardCache] = {}


def _read_existing_image_uri(path: Path) -> str:
    if not path.is_file() or path.stat().st_size <= 0:
        return ""
    return image_data_uri(path.read_bytes(), path.suffix)


async def _resolve_ranking_image_uri(url: str, local_path: Path | None, semaphore: asyncio.Semaphore) -> str:
    if local_path is not None:
        cached_uri = await to_thread(_read_existing_image_uri)(local_path)
        if cached_uri:
            return cached_uri
    if not url:
        return ""
    async with semaphore:
        path = await resolve_image(url, local_path)
    if path is None:
        return ""
    return await to_thread(_read_existing_image_uri)(path)


async def _load_avatar_images(avatar_ids: set[int], semaphore: asyncio.Semaphore) -> dict[int, str]:
    ordered = sorted(avatar_ids)
    uris = await asyncio.gather(
        *(
            _resolve_ranking_image_uri(avatar_image_url(avatar_id), local_avatar_image(avatar_id), semaphore)
            for avatar_id in ordered
        )
    )
    return {avatar_id: uri for avatar_id, uri in zip(ordered, uris, strict=True)}


async def _load_role_images(role_ids: set[int], semaphore: asyncio.Semaphore) -> dict[int, str]:
    ordered = sorted(role_ids)
    uris = await asyncio.gather(
        *(
            _resolve_ranking_image_uri(role_image_url(role_id), local_role_image(role_id), semaphore)
            for role_id in ordered
        )
    )
    return {role_id: uri for role_id, uri in zip(ordered, uris, strict=True)}


async def _load_tier_images(
    tier_indices: set[int],
    tier_mode: TierMode,
    semaphore: asyncio.Semaphore,
) -> dict[int, str]:
    ordered = sorted(tier_indices)
    if tier_mode == "challenge":
        uris = await asyncio.gather(
            *(
                _resolve_ranking_image_uri(
                    challenge_tier_image_url(idx),
                    local_challenge_tier_image(idx),
                    semaphore,
                )
                for idx in ordered
            )
        )
        return {idx: uri for idx, uri in zip(ordered, uris, strict=True)}
    uris = await asyncio.gather(
        *(_resolve_ranking_image_uri(tier_image_url(idx), local_tier_image(idx), semaphore) for idx in ordered)
    )
    return {idx: uri for idx, uri in zip(ordered, uris, strict=True)}


def _tier_mode_for_rank_type(rank_type: int) -> TierMode:
    if rank_type == 1:
        return "ranked"
    if rank_type == 7:
        return "challenge"
    return "none"


async def _build_assets(board: DakanuRankingsBoard, tier_mode: TierMode) -> RankingCardAssets:
    avatar_ids: set[int] = set()
    role_ids: set[int] = set()
    tier_indices: set[int] = set()
    for entry in board["entries"]:
        avatar_ids.add(entry["avatarId"])
        for role_id in entry["roles"][:3]:
            role_ids.add(role_id)
        segment = entry["segment"]
        if segment is not None and tier_mode != "none":
            idx = challenge_tier_index(segment) if tier_mode == "challenge" else tier_index(segment)
            if idx > 0:
                tier_indices.add(idx)

    semaphore = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)
    avatar_images, role_images, tier_images = await asyncio.gather(
        _load_avatar_images(avatar_ids, semaphore),
        _load_role_images(role_ids, semaphore),
        _load_tier_images(tier_indices, tier_mode, semaphore),
    )
    return RankingCardAssets(
        avatar_images=avatar_images,
        role_images=role_images,
        tier_images=tier_images,
    )


async def _fetch_ranking_bundle(
    rank_type: int,
    *,
    sub_type: int | None,
    include_floor: bool,
) -> tuple[DakanuRankingsBoard, DakanuRankingFloor | None, str]:
    if include_floor:
        board, floor, season = await asyncio.gather(
            fetch_rankings(rank_type=rank_type, page=1, page_size=50, sub_type=sub_type),
            fetch_ranking_floor(season_id=0),
            fetch_current_season(),
        )
    else:
        board, season = await asyncio.gather(
            fetch_rankings(rank_type=rank_type, page=1, page_size=50, sub_type=sub_type),
            fetch_current_season(),
        )
        floor = None
    season_label = season["ranked_season"]["label"] if season is not None else ""
    return board, floor, season_label


async def _load_role_names() -> dict[int, str]:
    remote_roles = await fetch_meta_roles()
    return {**remote_roles, **get_role_display_names()}


async def resolve_role_query(raw_query: str) -> tuple[int, str] | None:
    """按角色 ID、正式名、别名或拼音解析查询参数。"""
    query = raw_query.strip()
    if not query:
        return None

    roles = await _load_role_names()
    if query.isascii() and query.isdigit():
        role_id = int(query)
        if role_id in roles:
            return role_id, roles[role_id]
        return None

    for role_id, role_name in roles.items():
        if query == role_name:
            return role_id, role_name

    alias_role_id = resolve_role_alias(query, extra_roles=roles)
    if alias_role_id is not None and alias_role_id in roles:
        return alias_role_id, roles[alias_role_id]
    return None


async def build_role_board_usage_message() -> str:
    """构建超弦体单榜命令的用法提示与可选角色列表。"""
    try:
        roles = await _load_role_names()
    except DakanuError as exc:
        logger.warning(f"[卡拉彼丘·超弦体排行] 获取角色列表失败：{exc}")
        roles = get_role_display_names()

    if not roles:
        return _ROLE_USAGE_PREFIX
    available_roles = "、".join(roles[role_id] for role_id in sorted(roles))
    return f"{_ROLE_USAGE_PREFIX}\n可选角色：{available_roles}"


async def build_board_ranking_card(
    rank_type: int,
    *,
    sub_type: int | None = None,
    title_override: str | None = None,
    include_floor: bool = False,
    use_cache: bool = True,
) -> bytes:
    """拉取指定类型的排行榜前 50 名并渲染卡片，带 30 秒短时内存缓存。"""
    cache_key = (rank_type, sub_type)
    async with _board_cache_lock:
        now = time.monotonic()
        if use_cache and cache_key in _cached_board_cards and now < _cached_board_cards[cache_key].expires_at:
            return _cached_board_cards[cache_key].image

        board, floor, season_label = await _fetch_ranking_bundle(
            rank_type,
            sub_type=sub_type,
            include_floor=include_floor,
        )
        tier_mode = _tier_mode_for_rank_type(rank_type)
        assets = await _build_assets(board, tier_mode)
        image = await render_ranking_card(
            board,
            floor,
            season_label,
            assets,
            tier_mode=tier_mode,
            title_override=title_override,
        )
        _cached_board_cards[cache_key] = _RankingCardCache(
            expires_at=time.monotonic() + _CACHE_TTL_SECONDS,
            image=image,
        )
        return image


async def build_roles_ranking_card(
    *,
    sort_by: RolesSortBy = "winRate",
    ranked_only: bool = True,
    use_cache: bool = True,
) -> bytes:
    """拉取角色胜率与出场率排行并渲染卡片，带 30 秒短时内存缓存。"""
    cache_key = (sort_by, ranked_only)
    async with _roles_cache_lock:
        now = time.monotonic()
        if use_cache and cache_key in _cached_roles_cards and now < _cached_roles_cards[cache_key].expires_at:
            return _cached_roles_cards[cache_key].image

        board, remote_roles = await asyncio.gather(
            fetch_roles_ranking(ranked_only=ranked_only),
            fetch_meta_roles(),
        )
        role_names = {**remote_roles, **get_role_display_names()}
        role_ids = {entry["roleId"] for entry in board["entries"]}
        role_images = await _load_role_images(
            role_ids,
            asyncio.Semaphore(_DOWNLOAD_CONCURRENCY),
        )
        image = await render_roles_ranking_card(
            board,
            role_names,
            role_images,
            sort_by=sort_by,
        )
        _cached_roles_cards[cache_key] = _RankingCardCache(
            expires_at=time.monotonic() + _CACHE_TTL_SECONDS,
            image=image,
        )
        return image
