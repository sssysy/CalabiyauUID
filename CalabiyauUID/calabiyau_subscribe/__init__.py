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


@sv_subscribe.on_fullmatch(
    "订阅活动结束提醒",
    block=True,
    to_ai="""为当前群聊或私聊开启卡拉彼丘活动结束前 24 小时提醒

    当有权限的管理员要求在本会话开启活动结束提醒订阅时调用。

    Args:
        text: 无需参数，留空即可
    """,
    covers=["卡拉彼丘活动结束前24小时提醒订阅（管理员）"],
    aliases=["卡拉彼丘·开启活动提醒"],
)
async def calabiyau_subscribe_activity_end(bot: Bot, ev: Event) -> None:
    reply = await handle_subscribe_activity(ev)
    await bot.send(reply)


@sv_subscribe.on_fullmatch(
    "取消订阅活动结束提醒",
    block=True,
    to_ai="""取消当前群聊或私聊的卡拉彼丘活动结束提醒订阅

    当有权限的管理员要求取消本会话的活动结束提醒时调用。

    Args:
        text: 无需参数，留空即可
    """,
    covers=["卡拉彼丘活动结束提醒取消订阅（管理员）"],
    aliases=["卡拉彼丘·关闭活动提醒"],
)
async def calabiyau_unsubscribe_activity_end(bot: Bot, ev: Event) -> None:
    reply = await handle_unsubscribe_activity(ev)
    await bot.send(reply)


@scheduler.scheduled_job("interval", hours=2, id="klbq_activity_remind_sync")
async def scheduled_activity_remind_sync() -> None:
    await run_activity_remind_sync()


@on_core_start
async def on_start_activity_remind_sync() -> None:
    schedule_startup_activity_sync()
