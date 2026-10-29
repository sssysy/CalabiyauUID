"""卡拉彼丘数据刷新命令。"""

import asyncio

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .refresh_services import refresh_and_report, resolve_refresh_uid
from ..utils.helper.refresh import track_background

sv_refresh = SV("卡拉彼丘数据刷新")


@sv_refresh.on_command("刷新数据", block=True)
async def calabiyau_refresh_data(bot: Bot, ev: Event) -> None:
    player_id, error = await resolve_refresh_uid(ev)
    if error is not None:
        await bot.send(error)
        return
    await bot.send(f"已开始刷新 UID {player_id} 的战绩，通常需要 10～30 秒。\n完成后会在这个会话提醒你。")
    task = asyncio.create_task(refresh_and_report(bot, ev, player_id))
    track_background(task)
