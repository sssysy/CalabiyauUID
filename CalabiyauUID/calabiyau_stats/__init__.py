"""卡拉彼丘战绩命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .stats_services import resolve_player_id, build_summary_card
from ..utils.api.dakanu import DakanuError
from ..utils.helper.player_data import load_player_snapshot

sv_stats = SV("卡拉彼丘战绩查询")


@sv_stats.on_command("战绩总览", block=True)
async def calabiyau_stats_summary(bot: Bot, ev: Event) -> None:
    player_id, error = await resolve_player_id(ev)
    if error is not None:
        await bot.send(error)
        return

    snapshot = await load_player_snapshot(player_id)
    if snapshot is None:
        await bot.send("本地还没有这个玩家的战绩。\n发送 kq刷新数据 拉取后再查看。")
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
