"""战队目标解析、成员数据拉取与卡片渲染。"""

import asyncio
from dataclasses import dataclass

from gsuid_core.models import Event

from ..utils.downloader import resolve_image
from ..utils.helper.assets import local_avatar_image, read_image_data_uri
from ..utils.helper.refresh import (
    RefreshResult,
    ensure_player_snapshot,
    ensure_player_snapshot_with_fallback,
)
from ..utils.helper.ai_bridge import emit_ai_text
from ..utils.api.dakanu.assets import avatar_image_url
from ..utils.api.dakanu.client import DakanuError
from ..utils.helper.player_data import PlayerSnapshot
from ..utils.api.dakanu.requests import search_clans, fetch_clan_members
from ..utils.database.model_bind import get_main_uid
from ..utils.helper.player_resolve import is_numeric_uid
from ..utils.api.dakanu.models.clan import DakanuClan, DakanuClanMember
from ..utils.render.html.renderer.clan_card import render_clan_card

_DOWNLOAD_CONCURRENCY = 8


@dataclass(frozen=True)
class ClanTargetResult:
    clan: DakanuClan | None
    error: str | None
    player_id: str | None = None
    pending_task: asyncio.Task[RefreshResult] | None = None


async def _resolve_avatar_uri(avatar_id: int, semaphore: asyncio.Semaphore) -> str:
    local_path = local_avatar_image(avatar_id)
    cached = await read_image_data_uri(local_path)
    if cached:
        return cached
    async with semaphore:
        path = await resolve_image(avatar_image_url(avatar_id), local_path)
    return await read_image_data_uri(path)


async def _load_avatar_images(avatar_ids: set[int]) -> dict[int, str]:
    if not avatar_ids:
        return {}
    ordered = sorted(avatar_ids)
    semaphore = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)
    uris = await asyncio.gather(*(_resolve_avatar_uri(avatar_id, semaphore) for avatar_id in ordered))
    return {avatar_id: uri for avatar_id, uri in zip(ordered, uris, strict=True)}


def _format_clan_candidates(clans: list[DakanuClan], limit: int = 5) -> str:
    return "\n".join(f"- {clan.name}（ID：{clan.clanId}）" for clan in clans[:limit])


async def _resolve_by_query(query: str) -> DakanuClan:
    if is_numeric_uid(query):
        clans = await search_clans(clan_id=query, limit=10)
        matched = next((clan for clan in clans if clan.clanId == query), None)
        if matched is None:
            raise DakanuError(f"没有找到 ID 为「{query}」的战队。")
        return matched

    clans = await search_clans(name=query, limit=10)
    if not clans:
        raise DakanuError(f"没有找到名称包含「{query}」的战队。")

    exact_matches = [clan for clan in clans if clan.name == query]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        candidates = _format_clan_candidates(exact_matches)
        raise DakanuError(f"找到多个同名战队，请改用战队 ID：\n{candidates}")
    if len(clans) == 1:
        return clans[0]

    candidates = _format_clan_candidates(clans)
    raise DakanuError(f"找到多个匹配的战队，请输入完整战队名称或改用战队 ID：\n{candidates}")


async def resolve_clan_target_with_refresh(
    ev: Event,
    *,
    allow_stale_fallback: bool = True,
) -> ClanTargetResult:
    """按战队名/ID、@ 用户或当前绑定账号解析目标战队，并透传超时降级后的刷新任务。"""
    raw_query = ev.text.strip()
    if raw_query:
        try:
            clan = await _resolve_by_query(raw_query)
        except DakanuError as exc:
            return ClanTargetResult(clan=None, error=str(exc))
        return ClanTargetResult(clan=clan, error=None)

    at_target = ev.at.strip() if ev.at is not None else ""
    is_self_at = at_target in {ev.bot_id, ev.real_bot_id, ev.bot_self_id}
    target_user = ev.user_id if not at_target or is_self_at else at_target
    player_id = await get_main_uid(ev.bot_id, target_user)
    if player_id is None:
        if target_user == ev.user_id:
            return ClanTargetResult(
                clan=None,
                error="尚未绑定卡拉彼丘账号。\n发送 kq绑定 <UID 或昵称> 进行绑定，或发送 kq战队 <战队名或 ID> 查询。",
            )
        return ClanTargetResult(clan=None, error="对方尚未绑定卡拉彼丘账号。")

    pending_task: asyncio.Task[RefreshResult] | None = None
    try:
        if allow_stale_fallback:
            fetched = await ensure_player_snapshot_with_fallback(player_id)
            snapshot = fetched.snapshot
            pending_task = fetched.pending_task
        else:
            snapshot = await ensure_player_snapshot(player_id)
    except DakanuError as exc:
        return ClanTargetResult(clan=None, error=str(exc))

    clan_id = snapshot.profile.player.clanId.strip()
    if not clan_id:
        if target_user == ev.user_id:
            return ClanTargetResult(clan=None, error="当前账号暂未加入任何战队。")
        return ClanTargetResult(clan=None, error="对方账号暂未加入任何战队。")

    try:
        clan = await _resolve_by_query(clan_id)
    except DakanuError as exc:
        return ClanTargetResult(clan=None, error=str(exc))
    return ClanTargetResult(clan=clan, error=None, player_id=player_id, pending_task=pending_task)


async def resolve_clan_target(ev: Event) -> tuple[DakanuClan | None, str | None]:
    """按战队名/ID、@ 用户或当前绑定账号所在战队解析目标战队。"""
    result = await resolve_clan_target_with_refresh(ev, allow_stale_fallback=False)
    return result.clan, result.error


async def build_clan_card_from_snapshot(snapshot: PlayerSnapshot) -> bytes | None:
    """基于最新快照重新拉取并渲染玩家所在战队卡片；未加入战队时返回 None。"""
    clan_id = snapshot.profile.player.clanId.strip()
    if not clan_id:
        return None
    clan = await _resolve_by_query(clan_id)
    return await build_clan_card(clan)


def _format_clan_ai_summary(clan: DakanuClan, members: list[DakanuClanMember]) -> str:
    leaders = [member.nickname for member in members if member.isLeader]
    leader_text = "、".join(leaders) if leaders else "未知"
    intro = clan.intro.strip() or "暂无简介"
    member_preview = "、".join(
        f"{member.nickname}(Lv.{member.level if member.level is not None else '?'})" for member in members[:10]
    )
    lines: list[str] = [
        f"【战队信息：{clan.name}（ID：{clan.clanId}）】",
        f"等级：Lv.{clan.level} | 成员数：{clan.memberCount}（接口返回 {len(members)} 人） | 队长：{leader_text}",
        f"简介：{intro}",
    ]
    if member_preview:
        lines.append(f"成员示例（前 {min(10, len(members))} 人）：{member_preview}")
    return "\n".join(lines)


async def build_clan_card(clan: DakanuClan) -> bytes:
    """拉取战队成员与头像素材并渲染战队信息卡片。"""
    members_resp = await fetch_clan_members(clan.clanId)
    members = members_resp.members
    emit_ai_text(_format_clan_ai_summary(clan, members))
    avatar_ids = {member.avatarId for member in members if member.avatarId is not None}
    avatar_images = await _load_avatar_images(avatar_ids)
    return await render_clan_card(clan, members, avatar_images)
