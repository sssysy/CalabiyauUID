"""卡拉彼丘活动结束与兑换码订阅命令与定时调度。"""

from gsuid_core.sv import SV
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.server import on_core_start

from .subscribe_services import (
    run_cdkey_remind_sync,
    handle_subscribe_cdkey,
    handle_unsubscribe_cdkey,
    run_activity_remind_sync,
    handle_subscribe_activity,
    handle_unsubscribe_activity,
    schedule_startup_cdkey_sync,
    schedule_startup_activity_sync,
)

sv_subscribe = SV("卡拉彼丘活动订阅", pm=6)
sv_cdkey_subscribe = SV("卡拉彼丘兑换码订阅", pm=6)


@sv_subscribe.on_fullmatch(
    "订阅活动结束提醒",
    block=True,
    to_ai="""为当前群聊或私聊开启卡拉彼丘活动结束前 24 小时提醒

    当用户要求在本会话开启活动结束提醒订阅时调用。

    Args:
        text: 无需参数，留空即可
    """,
    covers=["卡拉彼丘活动结束前24小时提醒订阅"],
    aliases=["卡拉彼丘·开启活动提醒"],
)
async def calabiyau_subscribe_activity_end(bot: Bot, ev: Event) -> None:
    reply = await handle_subscribe_activity(ev)
    await bot.send(reply)


@sv_subscribe.on_fullmatch(
    "取消订阅活动结束提醒",
    block=True,
    to_ai="""取消当前群聊或私聊的卡拉彼丘活动结束提醒订阅

    当用户要求取消本会话的活动结束提醒时调用。

    Args:
        text: 无需参数，留空即可
    """,
    covers=["卡拉彼丘活动结束提醒取消订阅"],
    aliases=["卡拉彼丘·关闭活动提醒"],
)
async def calabiyau_unsubscribe_activity_end(bot: Bot, ev: Event) -> None:
    reply = await handle_unsubscribe_activity(ev)
    await bot.send(reply)


@sv_cdkey_subscribe.on_fullmatch(
    "订阅兑换码",
    block=True,
    to_ai="""为当前群聊或私聊开启卡拉彼丘新兑换码上线与临期 24 小时提醒订阅

    当用户要求在本会话开启兑换码提醒订阅时调用。

    Args:
        text: 无需参数，留空即可
    """,
    covers=["卡拉彼丘新兑换码推送与临期24小时提醒订阅"],
    aliases=["卡拉彼丘·开启兑换码订阅"],
)
async def calabiyau_subscribe_cdkey(bot: Bot, ev: Event) -> None:
    reply = await handle_subscribe_cdkey(ev)
    await bot.send(reply)


@sv_cdkey_subscribe.on_fullmatch(
    "取消订阅兑换码",
    block=True,
    to_ai="""取消当前群聊或私聊的卡拉彼丘兑换码提醒订阅

    当用户要求取消本会话的兑换码提醒时调用。

    Args:
        text: 无需参数，留空即可
    """,
    covers=["卡拉彼丘兑换码提醒取消订阅"],
    aliases=["卡拉彼丘·关闭兑换码订阅"],
)
async def calabiyau_unsubscribe_cdkey(bot: Bot, ev: Event) -> None:
    reply = await handle_unsubscribe_cdkey(ev)
    await bot.send(reply)


@scheduler.scheduled_job("interval", hours=2, id="klbq_activity_remind_sync", replace_existing=True)
async def scheduled_activity_remind_sync() -> None:
    await run_activity_remind_sync()


@on_core_start
async def on_start_activity_remind_sync() -> None:
    schedule_startup_activity_sync()


@scheduler.scheduled_job("interval", hours=2, id="klbq_cdkey_remind_sync", replace_existing=True)
async def scheduled_cdkey_remind_sync() -> None:
    await run_cdkey_remind_sync()


@on_core_start
async def on_start_cdkey_remind_sync() -> None:
    schedule_startup_cdkey_sync()
