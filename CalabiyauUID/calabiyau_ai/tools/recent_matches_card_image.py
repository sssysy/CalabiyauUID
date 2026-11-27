"""卡拉彼丘最近历史战绩卡片 AI 工具。"""

from gsuid_core.models import Event
from gsuid_core.ai_core.register import ai_tools

from ...utils.api.dakanu.client import DakanuError
from ...calabiyau_matches.matches_services import (
    resolve_match_player_id,
    build_recent_matches_card,
)


@ai_tools(
    category="common",
    capability_domain="卡拉彼丘战绩",
    context_tags=["卡拉彼丘", "游戏"],
    covers=["卡拉彼丘当前账号最近8场对局记录卡片、地图角色战绩与roomId"],
    aliases=["卡拉彼丘·最近战绩卡片", "卡拉彼丘·对局记录卡片"],
    timeout=120.0,
    background=True,
    background_grace=5.0,
)
async def calabiyau_recent_matches(ev: Event) -> bytes | str:
    """
    生成当前绑定卡拉彼丘账号最近 8 场历史战绩卡片。
    当用户想看最近几把打了什么、近期胜负或对局 KDA 时调用。
    """
    player_id, error = await resolve_match_player_id(ev)
    if error is not None:
        return error
    try:
        return await build_recent_matches_card(player_id)
    except DakanuError as exc:
        return str(exc)
    except RuntimeError:
        return "历史战绩卡片生成失败，请稍后再试。"
