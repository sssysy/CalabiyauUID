"""卡拉彼丘战绩命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .stats_services import (
    resolve_stats_query,
    render_summary_card_from_snapshot,
)
from ..utils.helper.refresh import (
    BUSY_FALLBACK_NOTICE,
    schedule_refreshed_card_push,
    ensure_player_snapshot_with_fallback,
)
from ..utils.api.dakanu.client import DakanuError

sv_stats = SV("卡拉彼丘战绩查询")


@sv_stats.on_command(
    "战绩总览",
    block=True,
)
async def calabiyau_stats_summary(bot: Bot, ev: Event) -> None:
    player_id, season, error = await resolve_stats_query(ev)
    if error is not None:
        await bot.send(error)
        return

    try:
        fetched = await ensure_player_snapshot_with_fallback(player_id)
        image = await render_summary_card_from_snapshot(fetched.snapshot, season=season)
    except DakanuError as exc:
        await bot.send(str(exc))
        return
    except RuntimeError:
        logger.exception("[卡拉彼丘·战绩总览] 渲染卡片失败")
        await bot.send("战绩卡片生成失败，请稍后再试。")
        return

    if fetched.pending_task is not None:
        await bot.send(BUSY_FALLBACK_NOTICE)
        await bot.send(image)
        schedule_refreshed_card_push(
            bot,
            fetched.pending_task,
            lambda snapshot: render_summary_card_from_snapshot(snapshot, season=season),
            feature_name="战绩总览",
            player_id=player_id,
        )
        return

    await bot.send(image)
