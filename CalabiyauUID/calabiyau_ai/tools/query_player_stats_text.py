"""纯文本卡拉彼丘玩家快照战绩与近期对局 roomId 查询工具。"""

from datetime import datetime

from gsuid_core.models import Event
from gsuid_core.ai_core.register import ai_tools

from ...utils.api.dakanu import DakanuError
from ...utils.helper.maps import resolve_map, resolve_role_name
from ...utils.helper.ai_bridge import format_player_snapshot_summary
from ...utils.helper.player_data import load_player_snapshot
from ...utils.database.model_bind import get_main_uid
from ...utils.helper.player_resolve import resolve_player_input
from ...utils.render.html.renderer.summary_card import (
    tier_display,
    challenge_tier_display,
    resolve_challenge_tier,
)

_RECENT_TEXT_LIMIT = 10


@ai_tools(
    category="common",
    capability_domain="卡拉彼丘战绩",
    context_tags=["卡拉彼丘", "游戏"],
    covers=[
        "卡拉彼丘玩家本地战绩快照纯文本摘要、排位与挑战段位、分模式统计、常用角色及最近10场roomId",
    ],
    aliases=["卡拉彼丘·纯文本查战绩", "卡拉彼丘·战绩分析数据"],
    timeout=30.0,
)
async def calabiyau_query_player_text(ev: Event, query: str = "") -> str:
    """
    以纯文本读取卡拉彼丘玩家的本地快照战绩与最近对局列表（不渲染图片）。
    适合需要快速获取数值做复盘、对比段位/胜率或提取对局 roomId 时调用；仅读取本地快照，不会自动刷新接口。

    Args:
        query: 目标玩家纯数字 UID 或游戏昵称；留空则自动读取当前用户绑定的主账号（如消息@了他人则读取被@者）
    """
    cleaned = query.strip()
    if cleaned:
        try:
            player_id = await resolve_player_input(cleaned)
        except DakanuError as exc:
            return f"解析目标玩家失败：{exc}"
    else:
        at_target = ev.at.strip() if ev.at is not None else ""
        is_self_at = at_target in {ev.bot_id, ev.real_bot_id, ev.bot_self_id}
        target_user = ev.user_id if not at_target or is_self_at else at_target
        bound_uid = await get_main_uid(ev.bot_id, target_user)
        if bound_uid is None:
            if target_user == ev.user_id:
                return "当前用户尚未绑定卡拉彼丘账号。请提供 UID/昵称，或先征询用户后调用绑定工具。"
            return "对方尚未绑定卡拉彼丘账号。请提供 UID 或游戏昵称。"
        player_id = bound_uid

    snapshot = await load_player_snapshot(player_id)
    if snapshot is None:
        return (
            f"本地还没有 UID {player_id} 的战绩缓存。"
            f"请先征询用户后调用刷新工具（kq刷新数据 {player_id}）拉取最新战绩。"
        )

    challenge_tier = resolve_challenge_tier(snapshot.leisure, snapshot.profile["presence"])
    challenge_label, _, _ = challenge_tier_display(challenge_tier)
    summary_text = format_player_snapshot_summary(
        snapshot,
        tier_name_fn=lambda segment: tier_display(segment)[0],
        challenge_label=challenge_label,
    )

    matches = snapshot.profile["matches"][:_RECENT_TEXT_LIMIT]
    if not matches:
        return f"{summary_text}\n近期对局列表为空。"

    match_lines: list[str] = [f"\n最近 {len(matches)} 场对局索引（可用于查询单局详情或下载回放）："]
    for idx, match in enumerate(matches, start=1):
        map_info = resolve_map(match["mapId"])
        map_name = map_info.name if map_info is not None else f"地图#{match['mapId']}"
        role_name = resolve_role_name(match["roleId"]) or f"角色#{match['roleId']}"
        score_text = (
            f"{match['myScore']}:{match['opponentScore']}"
            if match["myScore"] is not None and match["opponentScore"] is not None
            else "-"
        )
        played_str = datetime.fromtimestamp(match["playedAt"] / 1000).strftime("%m-%d %H:%M")
        match_lines.append(
            f"{idx}. [{match['result']}] {match['modeLabel']} · {map_name} · {role_name} | "
            f"{score_text} | KDA {match['kills']}/{match['deaths']}/{match['assists']} | "
            f"{played_str} | roomId={match['roomId']}"
        )
    return summary_text + "\n".join(match_lines)
