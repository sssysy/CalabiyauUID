"""卡拉彼丘玩家战绩强制刷新 AI 工具。"""

import time

from gsuid_core.models import Event
from gsuid_core.ai_core.register import ai_tools

from ...utils.helper.refresh import refresh_player_data
from ...utils.api.dakanu.client import DakanuError
from ...utils.database.model_bind import get_main_uid
from ...utils.helper.player_resolve import resolve_player_input


@ai_tools(
    category="common",
    capability_domain="卡拉彼丘战绩",
    context_tags=["卡拉彼丘", "游戏"],
    covers=["卡拉彼丘玩家战绩强制刷新与本地快照更新时间"],
    aliases=["卡拉彼丘·刷新战绩", "卡拉彼丘·更新数据"],
    timeout=120.0,
    background=True,
    background_grace=5.0,
)
async def calabiyau_refresh_player(ev: Event, query: str = "") -> str:
    """
    刷新卡拉彼丘玩家的最新战绩快照。
    当用户要求更新或刷新战绩数据时调用。

    Args:
        query: 目标玩家 UID 或游戏昵称；留空则刷新当前用户绑定的主账号
    """
    cleaned = query.strip()
    if cleaned:
        try:
            player_id = await resolve_player_input(cleaned)
        except DakanuError as exc:
            return f"刷新失败：{exc}"
    else:
        player_id = await get_main_uid(ev.bot_id, ev.user_id)
        if player_id is None:
            return "尚未绑定卡拉彼丘账号。\n发送 kq绑定 <UID 或昵称> 进行绑定。"
    try:
        result = await refresh_player_data(player_id, force=True)
    except (DakanuError, RuntimeError) as exc:
        return f"刷新失败：{exc}"
    saved_at = time.strftime("%Y-%m-%d %H:%M", time.localtime(result.snapshot.saved_at))
    return f"UID {player_id} 战绩刷新成功。\n本地快照时间：{saved_at}"
