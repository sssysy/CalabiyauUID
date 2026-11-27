"""卡拉彼丘账号绑定 AI 工具。"""

from gsuid_core.models import Event
from gsuid_core.ai_core.register import ai_tools

from ...utils.api.dakanu.client import DakanuError
from ...utils.helper.player_resolve import resolve_player_input
from ...calabiyau_bind.bind_services import bind_account


@ai_tools(
    category="common",
    capability_domain="卡拉彼丘账号",
    context_tags=["卡拉彼丘", "游戏"],
    covers=["卡拉彼丘国服账号绑定、UID/昵称解析及首次战绩快照拉取"],
    aliases=["卡拉彼丘·绑定账号", "卡拉彼丘·绑定UID"],
    timeout=120.0,
    background=True,
    background_grace=5.0,
)
async def calabiyau_bind_account(ev: Event, query: str) -> str:
    """
    绑定卡拉彼丘国服账号并拉取首次战绩快照。
    当用户要求绑定卡拉彼丘账号、关联游戏 UID 或游戏昵称时调用。

    Args:
        query: 卡拉彼丘纯数字 UID 或游戏昵称，例如 "1234567" 或 "星绘玩家"
    """
    cleaned = query.strip()
    if not cleaned:
        return "请提供要绑定的卡拉彼丘 UID 或游戏昵称。"
    try:
        game_uid = await resolve_player_input(cleaned)
        return await bind_account(ev.bot_id, ev.user_id, game_uid)
    except (DakanuError, RuntimeError) as exc:
        return f"绑定失败：{exc}"
