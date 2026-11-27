"""战绩总览的账号解析、本地快照读取与渲染编排。"""

import asyncio

from gsuid_core.models import Event

from ..utils.downloader import resolve_image
from ..utils.helper.maps import resolve_map
from ..utils.helper.assets import (
    local_role_image,
    local_tier_image,
    local_frame_image,
    local_avatar_image,
    read_image_data_uri,
    local_map_slug_image,
    local_baseplate_image,
    local_frame_index_image,
    local_challenge_tier_image,
)
from ..utils.helper.season import (
    ResolvedSeason,
    build_season_profile,
    resolve_season_query,
    split_season_and_target,
)
from ..utils.helper.refresh import ensure_player_snapshot as _ensure_fresh_snapshot
from ..utils.helper.ai_bridge import emit_ai_text, format_player_snapshot_summary
from ..utils.api.dakanu.assets import role_image_url, avatar_image_url
from ..utils.api.dakanu.client import DakanuError
from ..utils.helper.player_data import PlayerSnapshot
from ..utils.api.dakanu.requests import fetch_player_season
from ..utils.database.model_bind import get_main_uid
from ..utils.helper.player_resolve import resolve_player_input
from ..utils.helper.recent_matches import MatchView, load_recent_match_views
from ..utils.api.dakanu.models.player import DakanuProfile, DakanuPlayerSeason
from ..utils.render.html.renderer.summary_card import (
    SummaryAssets,
    tier_index,
    tier_display,
    render_summary_card,
    challenge_tier_display,
    resolve_challenge_tier,
    select_current_season_matches,
)


async def _resolve_target_player_id(ev: Event, raw_text: str) -> tuple[str, str | None]:
    if raw_text:
        try:
            player_id = await resolve_player_input(raw_text)
        except DakanuError as exc:
            return "", str(exc)
        return player_id, None

    at_target = ev.at.strip() if ev.at is not None else ""
    is_self_at = at_target in {ev.bot_id, ev.real_bot_id, ev.bot_self_id}
    target_user = ev.user_id if not at_target or is_self_at else at_target
    player_id = await get_main_uid(ev.bot_id, target_user)
    if player_id is not None:
        return player_id, None
    if target_user == ev.user_id:
        return "", "尚未绑定卡拉彼丘账号。\n发送 kq绑定 <UID 或昵称> 进行绑定。"
    return "", "对方尚未绑定卡拉彼丘账号。"


async def resolve_player_id(ev: Event) -> tuple[str, str | None]:
    """按 UID/昵称、@ 用户、当前账号的顺序解析查询目标。"""
    return await _resolve_target_player_id(ev, ev.text.strip())


async def resolve_stats_query(ev: Event) -> tuple[str, ResolvedSeason | None, str | None]:
    """从命令文本中解析可选赛季与查询目标玩家。"""
    season_token, target_text = split_season_and_target(ev.text)
    season: ResolvedSeason | None = None
    if season_token is not None:
        try:
            season = await resolve_season_query(season_token)
        except DakanuError as exc:
            return "", None, str(exc)
    player_id, error = await _resolve_target_player_id(ev, target_text)
    if error is not None:
        return "", None, error
    return player_id, season, None


async def ensure_player_snapshot(player_id: str, *, refresh: bool = False) -> PlayerSnapshot:
    return await _ensure_fresh_snapshot(player_id, force=refresh)


def format_snapshot_ai_summary(
    snapshot: PlayerSnapshot,
    *,
    profile_override: DakanuProfile | None = None,
    season_data: DakanuPlayerSeason | None = None,
) -> str:
    """从玩家快照提取供 AI 决策与复盘的结构化文本摘要。"""
    is_season_view = season_data is not None
    effective_leisure = season_data.leisure if season_data is not None else snapshot.leisure
    presence = None if is_season_view else snapshot.profile.presence
    challenge_tier = resolve_challenge_tier(effective_leisure, presence)
    challenge_label, _, _ = challenge_tier_display(challenge_tier)
    return format_player_snapshot_summary(
        snapshot,
        tier_name_fn=lambda segment: tier_display(segment)[0],
        challenge_label=challenge_label,
        profile_override=profile_override,
        is_season_view=is_season_view,
    )


async def render_snapshot_card(
    snapshot: PlayerSnapshot,
    *,
    season_data: DakanuPlayerSeason | None = None,
) -> bytes:
    is_season_view = season_data is not None
    profile = build_season_profile(snapshot.profile, season_data) if season_data is not None else snapshot.profile
    leisure = season_data.leisure if season_data is not None else snapshot.leisure
    emit_ai_text(
        format_snapshot_ai_summary(
            snapshot,
            profile_override=profile if is_season_view else None,
            season_data=season_data,
        )
    )
    avatar_id = profile.player.avatarId
    border_id = profile.player.borderId
    avatar_url = f"https://www.dakanu.com/avatars/{avatar_id}.webp"
    baseplate_url = f"https://www.dakanu.com/baseplates-lg/{avatar_id}.webp"
    frame_url = f"https://www.dakanu.com/frames-pc/{border_id}.webp"
    avatar_path = await resolve_image(avatar_url, local_avatar_image(avatar_id))
    baseplate_path = await resolve_image(baseplate_url, local_baseplate_image(avatar_id))
    frame_path = await resolve_image(frame_url, local_frame_image(border_id))
    avatar_frame_path = local_frame_index_image(border_id)
    rank_tier = tier_index(profile.rank.segment)
    top_tier = tier_index(profile.rank.historicalSegment)
    tier_path = local_tier_image(rank_tier) if rank_tier else None
    top_tier_path = local_tier_image(top_tier) if top_tier else None
    challenge_tier = resolve_challenge_tier(leisure, None if is_season_view else profile.presence)
    challenge_path = local_challenge_tier_image(challenge_tier) if challenge_tier else None
    if avatar_path is None or (rank_tier and tier_path is None) or (top_tier and top_tier_path is None):
        raise DakanuError("玩家图片读取失败，请稍后再试。")

    role_ids: list[int] = []
    for role in profile.roles[:5]:
        if role.roleId not in role_ids:
            role_ids.append(role.roleId)
    recent_match_views: list[MatchView] = []
    map_slugs: list[str] = []
    if not is_season_view:
        for match in profile.matches[:20]:
            role_id = match.roleId
            if role_id is not None and role_id > 0 and role_id not in role_ids:
                role_ids.append(role_id)
        season_matches = select_current_season_matches(profile)
        if season_matches:
            recent_match_views = await load_recent_match_views(
                profile.player.id,
                season_matches,
                limit=len(season_matches),
            )
            for view in recent_match_views:
                role_id = view.match.roleId
                if role_id is not None and role_id > 0 and role_id not in role_ids:
                    role_ids.append(role_id)
                map_info = resolve_map(view.match.mapId)
                if map_info is not None and map_info.slug and map_info.slug not in map_slugs:
                    map_slugs.append(map_info.slug)

    async def _load_role(role_id: int) -> tuple[int, str]:
        uri = await read_image_data_uri(local_role_image(role_id))
        if not uri:
            path = await resolve_image(role_image_url(role_id), local_role_image(role_id))
            uri = await read_image_data_uri(path)
        return role_id, uri

    rel_avatar_ids: list[int] = []
    if not is_season_view:
        for team_up in profile.teamUps[:5]:
            if team_up.avatarId > 0 and team_up.avatarId not in rel_avatar_ids:
                rel_avatar_ids.append(team_up.avatarId)
        for rival in profile.rivals[:5]:
            if rival.avatarId > 0 and rival.avatarId not in rel_avatar_ids:
                rel_avatar_ids.append(rival.avatarId)
        for view in recent_match_views:
            for team in view.teams:
                for roster_player in team.players:
                    roster_avatar_id = roster_player.avatarId
                    if roster_avatar_id > 0 and roster_avatar_id not in rel_avatar_ids:
                        rel_avatar_ids.append(roster_avatar_id)

    async def _load_avatar(rel_avatar_id: int) -> tuple[int, str]:
        uri = await read_image_data_uri(local_avatar_image(rel_avatar_id))
        if not uri:
            path = await resolve_image(avatar_image_url(rel_avatar_id), local_avatar_image(rel_avatar_id))
            uri = await read_image_data_uri(path)
        return rel_avatar_id, uri

    async def _load_map(slug: str) -> tuple[str, str]:
        uri = await read_image_data_uri(local_map_slug_image(slug))
        if not uri:
            path = await resolve_image(f"https://www.dakanu.com/maps-wide/{slug}.webp", local_map_slug_image(slug))
            uri = await read_image_data_uri(path)
        return slug, uri

    role_pairs, avatar_pairs, map_pairs = await asyncio.gather(
        asyncio.gather(*(_load_role(role_id) for role_id in role_ids)),
        asyncio.gather(*(_load_avatar(rel_avatar_id) for rel_avatar_id in rel_avatar_ids)),
        asyncio.gather(*(_load_map(slug) for slug in map_slugs)),
    )
    role_images: dict[int, str] = {role_id: uri for role_id, uri in role_pairs if uri}
    avatar_images: dict[int, str] = {rel_avatar_id: uri for rel_avatar_id, uri in avatar_pairs if uri}
    map_images: dict[str, str] = {slug: uri for slug, uri in map_pairs if uri}

    (
        avatar_uri,
        avatar_frame_uri,
        tier_uri,
        top_tier_uri,
        challenge_uri,
        baseplate_uri,
        frame_uri,
    ) = await asyncio.gather(
        read_image_data_uri(avatar_path),
        read_image_data_uri(avatar_frame_path),
        read_image_data_uri(tier_path),
        read_image_data_uri(top_tier_path),
        read_image_data_uri(challenge_path),
        read_image_data_uri(baseplate_path),
        read_image_data_uri(frame_path),
    )

    assets = SummaryAssets(
        avatar=avatar_uri,
        avatar_frame=avatar_frame_uri,
        tier_icon=tier_uri,
        top_tier_icon=top_tier_uri,
        challenge_icon=challenge_uri,
        baseplate=baseplate_uri,
        frame=frame_uri,
        role_images=role_images,
        clan_name=snapshot.clan.name if snapshot.clan is not None else "",
        leisure=leisure,
        avatar_images=avatar_images,
        map_images=map_images,
        recent_match_views=tuple(recent_match_views),
        is_season_view=is_season_view,
    )
    return await render_summary_card(profile, assets)


async def render_summary_card_from_snapshot(
    snapshot: PlayerSnapshot,
    *,
    season: ResolvedSeason | None = None,
) -> bytes:
    """基于给定快照渲染当前赛季或指定历史赛季战绩总览卡片。"""
    if season is None or season.current or season.season_id <= 0:
        return await render_snapshot_card(snapshot)
    season_data = await fetch_player_season(snapshot.profile.player.id, season.season_id)
    if season_data is None or season_data.summary.rounds <= 0:
        raise DakanuError(f"该玩家在 {season.label} 暂无战绩记录。")
    return await render_snapshot_card(snapshot, season_data=season_data)


async def build_summary_card(player_id: str, *, season: ResolvedSeason | None = None) -> bytes:
    """读取本地快照渲染；无快照或超过 1 天时静默拉取最新快照。"""
    snapshot = await ensure_player_snapshot(player_id)
    return await render_summary_card_from_snapshot(snapshot, season=season)
