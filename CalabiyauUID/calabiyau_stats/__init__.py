"""卡拉彼丘战绩命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .stats_services import resolve_player_id, build_summary_card
from ..utils.api.dakanu import DakanuError

sv_stats = SV("卡拉彼丘战绩查询")


@sv_stats.on_command(
    "战绩总览",
    block=True,
    to_ai="""查询卡拉彼丘玩家的生涯战绩总览卡片与数据摘要

    当用户想看自己或指定玩家的卡拉彼丘战绩总览、段位、胜率、KD、常用超弦体或生成战绩卡片时调用。
    优先读取本地快照；若本地无快照或已超过 1 天，会自动拉取最新快照。

    Args:
        text: 目标玩家 UID 或游戏昵称；留空则查询当前绑定主账号（如消息中@了他人则自动查被@者），例如 "" 或 "1234567"
    """,
    covers=["卡拉彼丘个人战绩总览卡片、排位/挑战段位、KD胜率及常用角色"],
    aliases=["卡拉彼丘·战绩查询", "卡拉彼丘·个人主页"],
)
async def calabiyau_stats_summary(bot: Bot, ev: Event) -> None:
    player_id, error = await resolve_player_id(ev)
    if error is not None:
        await bot.send(error)
        return

    try:
        image = await build_summary_card(player_id)
    except DakanuError as exc:
        await bot.send(str(exc))
        return
    except RuntimeError:
        logger.exception("[卡拉彼丘·战绩总览] 渲染卡片失败")
        await bot.send("战绩卡片生成失败，请稍后再试。")
        return

    await bot.send(image)
