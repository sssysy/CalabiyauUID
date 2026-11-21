"""卡拉彼丘战绩命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .stats_services import build_summary_card, resolve_stats_query
from ..utils.api.dakanu import DakanuError

sv_stats = SV("卡拉彼丘战绩查询")


@sv_stats.on_command(
    "战绩总览",
    block=True,
    to_ai="""查询卡拉彼丘玩家的生涯战绩总览卡片与数据摘要

    当用户想看自己或指定玩家的卡拉彼丘战绩总览、段位、胜率、KD、常用超弦体或生成战绩卡片时调用。
    支持指定赛季（如 s26ep5、26sp5、s26、s13）；当前赛季优先读取本地快照，历史赛季实时请求对应赛季接口。

    Args:
        text: 可选赛季名与/或目标玩家 UID/昵称；留空查当前赛季绑定主账号（@他人则查被@者），例如 ""、"s26ep5"、"26sp5 1234567" 或 "1234567 s13"
    """,
    covers=["卡拉彼丘个人战绩总览卡片、排位/挑战段位、KD胜率及常用角色"],
    aliases=["卡拉彼丘·战绩查询", "卡拉彼丘·个人主页"],
)
async def calabiyau_stats_summary(bot: Bot, ev: Event) -> None:
    player_id, season, error = await resolve_stats_query(ev)
    if error is not None:
        await bot.send(error)
        return

    try:
        image = await build_summary_card(player_id, season=season)
    except DakanuError as exc:
        await bot.send(str(exc))
        return
    except RuntimeError:
        logger.exception("[卡拉彼丘·战绩总览] 渲染卡片失败")
        await bot.send("战绩卡片生成失败，请稍后再试。")
        return

    await bot.send(image)
