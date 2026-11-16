"""卡拉彼丘活动结束提醒订阅命令与定时调度。"""

from gsuid_core.sv import SV
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.server import on_core_start

from .subscribe_services import (
    run_activity_remind_sync,
    handle_subscribe_activity,
    handle_unsubscribe_activity,
    schedule_startup_activity_sync,
)

sv_subscribe = SV("卡拉彼丘活动订阅", pm=6)


@sv_subscribe.on_fullmatch("订阅活动结束提醒", block=True)
async def calabiyau_subscribe_activity_end(bot: Bot, ev: Event) -> None:
    reply = await handle_subscribe_activity(ev)
    await bot.send(reply)


@sv_subscribe.on_fullmatch("取消订阅活动结束提醒", block=True)
async def calabiyau_unsubscribe_activity_end(bot: Bot, ev: Event) -> None:
    reply = await handle_unsubscribe_activity(ev)
    await bot.send(reply)


@scheduler.scheduled_job("interval", hours=2, id="klbq_activity_remind_sync")
async def scheduled_activity_remind_sync() -> None:
    await run_activity_remind_sync()


@on_core_start
async def on_start_activity_remind_sync() -> None:
    schedule_startup_activity_sync()
