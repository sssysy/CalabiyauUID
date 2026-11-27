"""历史战绩的账号解析、数据读取与卡片编排。"""

import asyncio
from pathlib import Path
from datetime import datetime

from gsuid_core.models import Event

from ..utils.downloader import resolve_image
from ..utils.helper.maps import MapInfo, resolve_map, resolve_role_name
from ..utils.helper.assets import (
    local_role_image,
    local_avatar_image,
    read_image_data_uri,
    local_map_slug_image,
)
from ..utils.helper.refresh import ensure_player_snapshot
from ..utils.helper.ai_bridge import emit_ai_text
from ..utils.api.dakanu.assets import role_image_url
from ..utils.api.dakanu.client import DakanuError
from ..utils.helper.player_data import PlayerSnapshot
from ..utils.database.model_bind import get_main_uid
from ..utils.helper.recent_matches import MatchView, load_recent_match_views
from ..utils.render.html.renderer.matches_card import MatchCardAssets, render_matches_card

_RECENT_LIMIT = 8


async def resolve_match_player_id(ev: Event) -> tuple[str, str | None]:
    """历史战绩只查询当前账号。"""
    player_id = await get_main_uid(ev.bot_id, ev.user_id)
    if player_id is None:
        return "", "尚未绑定卡拉彼丘账号。\n发送 kq绑定 <UID> 进行绑定。"
    return player_id, None


async def _load_recent_matches_data(player_id: str) -> tuple[PlayerSnapshot, list[MatchView]]:
    snapshot = await ensure_player_snapshot(player_id)
    matches = snapshot.profile.matches
    if not matches:
        raise DakanuError("历史战绩为空。\n发送 kq刷新数据 更新后再查看。")
    views = await load_recent_match_views(player_id, matches, _RECENT_LIMIT)
    return snapshot, views


async def load_recent_matches(player_id: str) -> list[MatchView]:
    _, views = await _load_recent_matches_data(player_id)
    return views


def _avatar_url(avatar_id: int) -> str:
    return f"https://www.dakanu.com/avatars/{avatar_id}.webp"


def _map_url(slug: str) -> str:
    return f"https://www.dakanu.com/maps-wide/{slug}.webp"


async def _resolve_image_uri(url: str, local_path: Path | None) -> str:
    cached = await read_image_data_uri(local_path)
    if cached:
        return cached
    path = await resolve_image(url, local_path)
    return await read_image_data_uri(path)


async def _load_avatar_images(avatar_ids: set[int]) -> dict[int, str]:
    ordered = sorted(avatar_ids)
    uris = await asyncio.gather(
        *(_resolve_image_uri(_avatar_url(avatar_id), local_avatar_image(avatar_id)) for avatar_id in ordered)
    )
    return {avatar_id: uri for avatar_id, uri in zip(ordered, uris, strict=True)}


async def _load_role_images(role_ids: set[int]) -> dict[int, str]:
    ordered = sorted(role_ids)
    uris = await asyncio.gather(
        *(_resolve_image_uri(role_image_url(role_id), local_role_image(role_id)) for role_id in ordered)
    )
    return {role_id: uri for role_id, uri in zip(ordered, uris, strict=True)}


async def _load_map_images(map_infos: list[MapInfo]) -> dict[str, str]:
    unique_maps: dict[str, MapInfo] = {}
    for map_info in map_infos:
        if map_info.slug and map_info.slug not in unique_maps:
            unique_maps[map_info.slug] = map_info
    slugs = sorted(unique_maps)
    uris = await asyncio.gather(*(_resolve_image_uri(_map_url(slug), local_map_slug_image(slug)) for slug in slugs))
    return {slug: uri for slug, uri in zip(slugs, uris, strict=True)}


async def _build_assets(snapshot: PlayerSnapshot, views: list[MatchView]) -> MatchCardAssets:
    player = snapshot.profile.player
    avatar_ids: set[int] = {player.avatarId}
    role_ids: set[int] = set()
    map_infos: list[MapInfo] = []
    for view in views:
        role_id = view.match.roleId
        if role_id is not None and role_id > 0:
            role_ids.add(role_id)
        map_info = resolve_map(view.match.mapId)
        if map_info is not None:
            map_infos.append(map_info)
        for team in view.teams:
            for roster_player in team.players:
                avatar_ids.add(roster_player.avatarId)

    avatar_images, role_images, map_images = await asyncio.gather(
        _load_avatar_images(avatar_ids),
        _load_role_images(role_ids),
        _load_map_images(map_infos),
    )
    player_avatar = avatar_images[player.avatarId] if player.avatarId in avatar_images else ""
    clan_name = snapshot.clan.name if snapshot.clan is not None else ""
    return MatchCardAssets(
        player_avatar=player_avatar,
        avatar_images=avatar_images,
        role_images=role_images,
        map_images=map_images,
        clan_name=clan_name,
    )


def format_recent_matches_ai_summary(snapshot: PlayerSnapshot, views: list[MatchView]) -> str:
    """提取最近对局摘要供 AI 复盘及衔接单局详情或回放下载。"""
    player = snapshot.profile.player
    saved_time = datetime.fromtimestamp(snapshot.saved_at).strftime("%Y-%m-%d %H:%M")
    lines: list[str] = [f"【{player.nickname}（UID：{player.id}）最近 {len(views)} 场历史战绩】"]
    for idx, view in enumerate(views, start=1):
        match = view.match
        map_info = resolve_map(match.mapId)
        map_name = map_info.name if map_info is not None else f"地图#{match.mapId}"
        role_id = match.roleId
        role_name = (resolve_role_name(role_id) or f"角色#{role_id}") if role_id is not None else "未知角色"
        score_text = (
            f"{match.myScore}:{match.opponentScore}"
            if match.myScore is not None and match.opponentScore is not None
            else "-"
        )
        delta_text = ""
        if match.divisionScoreDelta is not None:
            sign = "+" if match.divisionScoreDelta > 0 else ""
            delta_text = f" 分数{sign}{match.divisionScoreDelta}"
        badge = " [MVP]" if match.mvp else (" [SVP]" if match.svp else "")
        played_str = (
            datetime.fromtimestamp(match.playedAt / 1000).strftime("%m-%d %H:%M") if match.playedAt is not None else "-"
        )
        duration_text = f"{match.durationSeconds}s" if match.durationSeconds is not None else "-"
        kda_text = (
            f"{match.kills}/{match.deaths}/{match.assists}"
            if match.kills is not None and match.deaths is not None and match.assists is not None
            else "-"
        )
        lines.append(
            f"{idx}. [{match.result}] {match.modeLabel} · {map_name} · {role_name} | "
            f"比分 {score_text} | KDA {kda_text}{badge}{delta_text} | "
            f"时长 {duration_text} | {played_str} | roomId={match.roomId}"
        )
    lines.append(f"本地快照时间：{saved_time}")
    return "\n".join(lines)


async def build_recent_matches_card_from_snapshot(snapshot: PlayerSnapshot) -> bytes:
    """基于给定快照渲染最近历史战绩卡片。"""
    player_id = snapshot.profile.player.id
    matches = snapshot.profile.matches
    if not matches:
        raise DakanuError("历史战绩为空。\n发送 kq刷新数据 更新后再查看。")
    views = await load_recent_match_views(player_id, matches, _RECENT_LIMIT)
    emit_ai_text(format_recent_matches_ai_summary(snapshot, views))
    assets = await _build_assets(snapshot, views)
    return await render_matches_card(snapshot.profile, views, assets)


async def build_recent_matches_card(player_id: str) -> bytes:
    snapshot = await ensure_player_snapshot(player_id)
    return await build_recent_matches_card_from_snapshot(snapshot)
