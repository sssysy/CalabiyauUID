"""卡拉彼丘战绩总览卡片 AI 工具。"""

from gsuid_core.models import Event
from gsuid_core.ai_core.register import ai_tools

from ...utils.api.dakanu.client import DakanuError
from ...calabiyau_stats.stats_services import build_summary_card, resolve_stats_params


@ai_tools(
    category="common",
    capability_domain="卡拉彼丘战绩",
    context_tags=["卡拉彼丘", "游戏"],
    covers=["卡拉彼丘个人战绩总览卡片、排位/挑战段位、KD胜率及常用角色"],
    aliases=["卡拉彼丘·战绩卡片", "卡拉彼丘·个人主页"],
    timeout=120.0,
    background=True,
    background_grace=5.0,
)
async def calabiyau_stats_summary(ev: Event, query: str = "", season: str = "") -> bytes | str:
    """
    生成卡拉彼丘玩家战绩总览卡片。
    当用户想看战绩总览、段位、胜率、KD 或常用角色卡片时调用。

    Args:
        query: 可选赛季名与/或目标玩家 UID/昵称；留空查当前赛季绑定主账号
        season: 可选赛季名，例如 "s26ep5"、"26sp5"、"s26"、"s13"
    """
    player_id, resolved_season, error = await resolve_stats_params(ev, query, season_token=season)
    if error is not None:
        return error
    try:
        return await build_summary_card(player_id, season=resolved_season)
    except DakanuError as exc:
        return str(exc)
    except RuntimeError:
        return "战绩卡片生成失败，请稍后再试。"
