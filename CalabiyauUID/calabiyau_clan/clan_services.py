"""战队目标解析、成员数据拉取与卡片渲染。"""

import asyncio
from pathlib import Path

from gsuid_core.pool import to_thread
from gsuid_core.models import Event

from ..utils.api.dakanu import (
    DakanuClan,
    DakanuError,
    DakanuClanMember,
    search_clans,
    avatar_image_url,
    fetch_clan_members,
)
from ..utils.downloader import resolve_image
from ..utils.helper.assets import image_data_uri, local_avatar_image
from ..utils.helper.ai_bridge import emit_ai_text
from ..utils.helper.player_data import load_player_snapshot
from ..utils.database.model_bind import get_main_uid
from ..utils.helper.player_resolve import is_numeric_uid
from ..utils.render.html.renderer.clan_card import render_clan_card

_DOWNLOAD_CONCURRENCY = 8


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


async def _load_avatar_images(avatar_ids: set[int]) -> dict[int, str]:
    if not avatar_ids:
        return {}
    ordered = sorted(avatar_ids)
    semaphore = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)
    uris = await asyncio.gather(*(_resolve_avatar_uri(avatar_id, semaphore) for avatar_id in ordered))
    return {avatar_id: uri for avatar_id, uri in zip(ordered, uris, strict=True)}


def _format_clan_candidates(clans: list[DakanuClan], limit: int = 5) -> str:
    return "\n".join(f"- {clan['name']}（ID：{clan['clanId']}）" for clan in clans[:limit])


async def _resolve_by_query(query: str) -> DakanuClan:
    if is_numeric_uid(query):
        clans = await search_clans(clan_id=query, limit=10)
        matched = next((clan for clan in clans if clan["clanId"] == query), None)
        if matched is None:
            raise DakanuError(f"没有找到 ID 为「{query}」的战队。")
        return matched

    clans = await search_clans(name=query, limit=10)
    if not clans:
        raise DakanuError(f"没有找到名称包含「{query}」的战队。")

    exact_matches = [clan for clan in clans if clan["name"] == query]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        candidates = _format_clan_candidates(exact_matches)
        raise DakanuError(f"找到多个同名战队，请改用战队 ID：\n{candidates}")
    if len(clans) == 1:
        return clans[0]

    candidates = _format_clan_candidates(clans)
    raise DakanuError(f"找到多个匹配的战队，请输入完整战队名称或改用战队 ID：\n{candidates}")


async def resolve_clan_target(ev: Event) -> tuple[DakanuClan | None, str | None]:
    """按战队名/ID、@ 用户或当前绑定账号所在战队解析目标战队。"""
    raw_query = ev.text.strip()
    if raw_query:
        try:
            clan = await _resolve_by_query(raw_query)
        except DakanuError as exc:
            return None, str(exc)
        return clan, None

    at_target = ev.at.strip() if ev.at is not None else ""
    is_self_at = at_target in {ev.bot_id, ev.real_bot_id, ev.bot_self_id}
    target_user = ev.user_id if not at_target or is_self_at else at_target
    player_id = await get_main_uid(ev.bot_id, target_user)
    if player_id is None:
        if target_user == ev.user_id:
            return None, "尚未绑定卡拉彼丘账号。\n发送 kq绑定 <UID 或昵称> 进行绑定，或发送 kq战队 <战队名或 ID> 查询。"
        return None, "对方尚未绑定卡拉彼丘账号。"

    snapshot = await load_player_snapshot(player_id)
    if snapshot is None:
        return (
            None,
            f"本地还没有该玩家的战绩缓存（UID：{player_id}）。\n"
            f"请先发送 kq刷新数据 {player_id} 拉取后再查看，或发送 kq战队 <战队名或 ID> 查询。",
        )

    clan_id = snapshot.profile["player"]["clanId"].strip()
    if not clan_id:
        if target_user == ev.user_id:
            return None, "当前账号暂未加入任何战队。"
        return None, "对方账号暂未加入任何战队。"

    try:
        clan = await _resolve_by_query(clan_id)
    except DakanuError as exc:
        return None, str(exc)
    return clan, None


def _format_clan_ai_summary(clan: DakanuClan, members: list[DakanuClanMember]) -> str:
    leaders = [member["nickname"] for member in members if member["isLeader"]]
    leader_text = "、".join(leaders) if leaders else "未知"
    intro = clan["intro"].strip() or "暂无简介"
    member_preview = "、".join(
        f"{member['nickname']}(Lv.{member['level'] if member['level'] is not None else '?'})"
        for member in members[:10]
    )
    lines: list[str] = [
        f"【战队信息：{clan['name']}（ID：{clan['clanId']}）】",
        f"等级：Lv.{clan['level']} | 成员数：{clan['memberCount']}（接口返回 {len(members)} 人） | 队长：{leader_text}",
        f"简介：{intro}",
    ]
    if member_preview:
        lines.append(f"成员示例（前 {min(10, len(members))} 人）：{member_preview}")
    return "\n".join(lines)


async def build_clan_card(clan: DakanuClan) -> bytes:
    """拉取战队成员与头像素材并渲染战队信息卡片。"""
    members_resp = await fetch_clan_members(clan["clanId"])
    members = members_resp["members"]
    emit_ai_text(_format_clan_ai_summary(clan, members))
    avatar_ids = {member["avatarId"] for member in members if member["avatarId"] is not None}
    avatar_images = await _load_avatar_images(avatar_ids)
    return await render_clan_card(clan, members, avatar_images)
