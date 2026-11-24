"""单场卡拉彼丘对局完整记分板与双方阵容查询工具。"""

from gsuid_core.models import Event
from gsuid_core.ai_core.register import ai_tools

from ...utils.api.dakanu import (
    DakanuError,
    DakanuMatchTeam,
    DakanuMatchPlayer,
    is_valid_room_id,
)
from ...utils.helper.match_cache import get_match_detail
from ...utils.database.model_bind import get_main_uid
from ...utils.helper.player_resolve import resolve_player_input


def _format_player_row(player: DakanuMatchPlayer) -> str:
    badges: list[str] = []
    if player["isTarget"]:
        badges.append("视角")
    if player["mvp"]:
        badges.append("MVP")
    elif player["svp"]:
        badges.append("SVP")
    badge_text = f" [{'/'.join(badges)}]" if badges else ""
    kd_suffix = f"/倒地{player['knockdowns']}" if player["knockdowns"] is not None else ""
    return (
        f"- {player['nickname']}（{player['roleName']}）{badge_text}："
        f"K/D/A {player['kills']}/{player['deaths']}/{player['assists']}{kd_suffix}，"
        f"伤害 {player['damage']}，评分 {player['score']}"
    )


def _format_team_block(team: DakanuMatchTeam) -> list[str]:
    lines: list[str] = [f"【{team['label']}（{team['id']}）】"]
    for player in team["players"]:
        lines.append(_format_player_row(player))
    return lines


@ai_tools(
    category="common",
    capability_domain="卡拉彼丘战绩",
    context_tags=["卡拉彼丘", "游戏"],
    covers=[
        "卡拉彼丘单局对局详细记分板、双方阵容超弦体、击杀倒地助攻死亡、总伤害与MVP/SVP评分",
    ],
    aliases=["卡拉彼丘·单局详情", "卡拉彼丘·对局复盘数据"],
    timeout=30.0,
)
async def calabiyau_query_match_detail(
    ev: Event,
    room_id: str,
    player_query: str = "",
) -> str:
    """
    查询指定卡拉彼丘对局（roomId）的完整双方记分板与伤害数据。
    当用户要求分析某一场比赛发挥、查看队友/对手战绩或对比单局伤害时调用。

    Args:
        room_id: 纯数字对局 roomId，可从战绩或历史战绩摘要中获得
        player_query: 视角玩家 UID 或昵称；留空则使用当前用户绑定的主账号
    """
    cleaned_room = room_id.strip()
    if not is_valid_room_id(cleaned_room):
        return f"无效的对局 ID：{room_id}。roomId 应为非零开头的纯数字（最多 20 位）。"

    cleaned_player = player_query.strip()
    if cleaned_player:
        try:
            player_id = await resolve_player_input(cleaned_player)
        except DakanuError as exc:
            return f"解析视角玩家失败：{exc}"
    else:
        bound_uid = await get_main_uid(ev.bot_id, ev.user_id)
        if bound_uid is None:
            return "当前用户尚未绑定账号，请提供视角玩家 UID/昵称（player_query）。"
        player_id = bound_uid

    try:
        detail = await get_match_detail(player_id, cleaned_room)
    except DakanuError as exc:
        return f"获取对局 {cleaned_room} 详情失败：{exc}"

    if detail is None:
        return f"暂未收录对局 {cleaned_room} 的详细记分板数据。"

    teams = detail["teams"] if "teams" in detail else []
    if not teams:
        return f"对局 {cleaned_room} 暂无双方阵容明细。"

    lines: list[str] = [f"【卡拉彼丘单局详情 roomId={cleaned_room}（视角 UID：{player_id}）】"]
    for team in teams:
        lines.extend(_format_team_block(team))
    return "\n".join(lines)
