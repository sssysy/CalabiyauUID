"""战绩总览的账号解析、本地快照读取与渲染编排。"""

import base64
from pathlib import Path

from gsuid_core.models import Event

from ..utils.api.dakanu import DakanuError, role_image_url
from ..utils.downloader import resolve_image
from ..utils.helper.assets import (
    local_role_image,
    local_tier_image,
    local_frame_image,
    local_avatar_image,
    local_baseplate_image,
    local_challenge_tier_image,
)
from ..utils.helper.refresh import refresh_player_data
from ..utils.helper.player_data import PlayerSnapshot, load_player_snapshot
from ..utils.database.model_bind import CalabiyauBind
from ..utils.render.html.summary_card import (
    SummaryAssets,
    tier_index,
    render_summary_card,
    challenge_tier_index,
)


async def _main_uid(bot_id: str, user_id: str) -> str | None:
    binds = await CalabiyauBind.get_binds(bot_id, user_id)
    if not binds:
        return None
    current = next((bind for bind in binds if bind.is_main), binds[0])
    return current.game_uid


async def resolve_player_id(ev: Event) -> tuple[str, str | None]:
    """按 UID、@ 用户、当前账号的顺序解析查询目标。"""
    raw_text = ev.text.strip()
    if raw_text:
        if not raw_text.isdigit():
            return "", "请在命令后附带卡拉彼丘 UID。\n例如：kq战绩总览 1234567"
        return raw_text, None

    at_target = ev.at.strip() if ev.at is not None else ""
    is_self_at = at_target in {ev.bot_id, ev.real_bot_id, ev.bot_self_id}
    target_user = ev.user_id if not at_target or is_self_at else at_target
    player_id = await _main_uid(ev.bot_id, target_user)
    if player_id is not None:
        return player_id, None
    if target_user == ev.user_id:
        return "", "尚未绑定卡拉彼丘账号。\n发送 kq绑定 <UID> 进行绑定。"
    return "", "对方尚未绑定卡拉彼丘账号。"


async def ensure_player_snapshot(player_id: str, *, refresh: bool = False) -> PlayerSnapshot:
    return (await refresh_player_data(player_id, force=refresh)).snapshot


async def render_snapshot_card(snapshot: PlayerSnapshot) -> bytes:
    profile = snapshot.profile
    leisure = snapshot.leisure
    avatar_id = profile["player"]["avatarId"]
    avatar_url = f"https://www.dakanu.com/avatars/{avatar_id}.webp"
    baseplate_url = f"https://www.dakanu.com/baseplates-lg/{avatar_id}.webp"
    frame_url = f"https://www.dakanu.com/frames-pc/{profile['player']['borderId']}.webp"
    avatar_path = await resolve_image(avatar_url, local_avatar_image(avatar_id))
    baseplate_path = await resolve_image(baseplate_url, local_baseplate_image(avatar_id))
    frame_path = await resolve_image(frame_url, local_frame_image(profile["player"]["borderId"]))
    rank_tier = tier_index(profile["rank"]["segment"])
    top_tier = tier_index(profile["rank"]["topSegment"])
    tier_path = local_tier_image(rank_tier) if rank_tier else None
    top_tier_path = local_tier_image(top_tier) if top_tier else None
    challenge_tier = challenge_tier_index(leisure["segment"]) if leisure is not None and "segment" in leisure else 0
    challenge_path = local_challenge_tier_image(challenge_tier) if challenge_tier else None
    if avatar_path is None or (rank_tier and tier_path is None) or (top_tier and top_tier_path is None):
        raise DakanuError("玩家图片读取失败，请稍后再试。")
    role_paths: list[Path | None] = []
    for role in profile["roles"][:5]:
        role_id = role["roleId"]
        role_url = role_image_url(role_id)
        role_paths.append(await resolve_image(role_url, local_role_image(role_id)))

    assets = SummaryAssets(
        avatar=_data_uri(avatar_path.read_bytes(), avatar_path.suffix),
        tier_icon=_data_uri(tier_path.read_bytes(), tier_path.suffix) if tier_path is not None else "",
        top_tier_icon=_data_uri(top_tier_path.read_bytes(), top_tier_path.suffix) if top_tier_path is not None else "",
        challenge_icon=_data_uri(challenge_path.read_bytes(), challenge_path.suffix)
        if challenge_path is not None
        else "",
        baseplate=_data_uri(baseplate_path.read_bytes(), baseplate_path.suffix) if baseplate_path is not None else "",
        frame=_data_uri(frame_path.read_bytes(), frame_path.suffix) if frame_path is not None else "",
        role_images=tuple(_data_uri(path.read_bytes(), path.suffix) if path is not None else "" for path in role_paths),
        clan_name=snapshot.clan["name"] if snapshot.clan is not None else "",
        leisure=leisure,
    )
    return await render_summary_card(profile, assets)


async def build_summary_card(player_id: str) -> bytes:
    """只读本地快照渲染；没有快照时提示先刷新。"""
    snapshot = await load_player_snapshot(player_id)
    if snapshot is None:
        raise DakanuError("本地还没有这个玩家的战绩。\n请先发送 kq刷新数据 拉取。")
    return await render_snapshot_card(snapshot)


def _data_uri(content: bytes, suffix: str) -> str:
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(suffix.lower(), "image/webp")
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"
