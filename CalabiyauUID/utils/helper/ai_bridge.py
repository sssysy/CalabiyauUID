"""AI 触发器文本回传的惰性调用封装。"""

import sys
from datetime import datetime
from collections.abc import Callable

from gsuid_core.ai_core.configs.ai_config import ai_config

from .maps import resolve_role_name
from .player_data import PlayerSnapshot


def emit_ai_text(text: str) -> None:
    """仅在 AI 启用或桥接模块已加载时回传文本，避免关闭 AI 时加载 pydantic_ai。"""
    if not text:
        return
    if "gsuid_core.ai_core.trigger_bridge" not in sys.modules and not ai_config.get_config("enable").data:
        return
    from gsuid_core.ai_core.trigger_bridge import ai_return

    ai_return(text)


def format_player_snapshot_summary(
    snapshot: PlayerSnapshot,
    *,
    tier_name_fn: Callable[[int], str],
    challenge_label: str = "",
) -> str:
    """从玩家快照提取供 AI 决策与复盘的结构化文本摘要。"""
    profile = snapshot.profile
    player = profile["player"]
    rank = profile["rank"]
    summary = profile["summary"]
    presence = profile["presence"]
    tier_label = tier_name_fn(rank["segment"])
    top_tier_label = tier_name_fn(rank["historicalSegment"])
    saved_time = datetime.fromtimestamp(snapshot.saved_at).strftime("%Y-%m-%d %H:%M")
    clan_name = snapshot.clan["name"] if snapshot.clan is not None else (player["clanId"] or "无")
    rank_pos = str(rank["rankPos"]) if rank["rankPos"] is not None else "未上榜"

    lines: list[str] = [
        f"【卡拉彼丘战绩总览：{player['nickname']}（UID：{player['id']}）】",
        f"等级：Lv.{player['level']} | 战队：{clan_name} | 在线状态：{presence['state']} | 隐私：{player['privacyStatus']}",
        f"排位段位：{tier_label}（{rank['divisionScore']} 分，历史最高：{top_tier_label}，排名：{rank_pos}）",
    ]
    if challenge_label:
        lines.append(f"挑战段位：{challenge_label}")
    lines.append(
        "生涯总览："
        f"{summary['rounds']} 场 / {summary['wins']} 胜（胜率 {summary['winRate'] * 100:.1f}%），"
        f"KD {summary['kd']:.2f}，KDA {summary['kda']:.2f}，"
        f"场均伤害 {summary['avgDamage']:.0f}，回合均伤 {summary['roundAveDamage']:.0f}，"
        f"MVP 率 {summary['mvpRate'] * 100:.1f}%，爆头率 {summary['headshotRate'] * 100:.1f}%"
    )
    if profile["modes"]:
        mode_parts = [
            f"{mode['label']}({mode['rounds']}场/胜率{mode['winRate'] * 100:.1f}%/KD {mode['kd']:.2f})"
            for mode in profile["modes"][:5]
        ]
        lines.append("分模式：" + "；".join(mode_parts))
    if profile["roles"]:
        role_parts = [
            (
                f"{resolve_role_name(role['roleId']) or role['name']}"
                f"({role['count']}场/胜率{role['winRate'] * 100:.1f}%/KD {role['kd']:.2f}/均伤{role['avgDamage']:.0f})"
            )
            for role in profile["roles"][:5]
        ]
        lines.append("常用超弦体 Top5：" + "；".join(role_parts))
    lines.append(f"本地快照时间：{saved_time}（如需最新数据请先刷新）")
    return "\n".join(lines)
