"""卡拉彼丘 Fanbook 每日签到命令与定时任务。"""

from gsuid_core.sv import SV
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.server import on_core_start

from .sign_services import (
    parse_sign_time,
    enable_auto_sign,
    disable_auto_sign,
    query_fanbook_points,
    run_all_fanbook_sign,
    run_manual_fanbook_sign,
    run_scheduled_fanbook_sign,
    schedule_startup_fanbook_sign,
)

sv_fanbook_sign = SV("卡拉彼丘Fanbook签到")
sv_fanbook_sign_all = SV("卡拉彼丘Fanbook全部签到", pm=1)

_SIGN_HOUR, _SIGN_MINUTE = parse_sign_time()


@sv_fanbook_sign.on_fullmatch("签到", block=True)
async def calabiyau_fanbook_sign(bot: Bot, ev: Event) -> None:
    await bot.send("[卡丘] 开始签到任务，请稍后......", at_sender=bool(ev.group_id))
    reply = await run_manual_fanbook_sign(ev.bot_id, ev.user_id)
    await bot.send(reply, at_sender=bool(ev.group_id))


@sv_fanbook_sign.on_fullmatch("积分", block=True)
async def calabiyau_fanbook_points(bot: Bot, ev: Event) -> None:
    reply = await query_fanbook_points(ev.bot_id, ev.user_id)
    if ev.group_id:
        reply = f"\n{reply}"
    await bot.send(reply, at_sender=bool(ev.group_id))


@sv_fanbook_sign.on_fullmatch("开启自动签到", block=True)
async def calabiyau_fanbook_auto_sign_on(bot: Bot, ev: Event) -> None:
    reply = await enable_auto_sign(ev)
    await bot.send(reply, at_sender=bool(ev.group_id))


@sv_fanbook_sign.on_fullmatch("关闭自动签到", block=True)
async def calabiyau_fanbook_auto_sign_off(bot: Bot, ev: Event) -> None:
    reply = await disable_auto_sign(ev)
    await bot.send(reply, at_sender=bool(ev.group_id))


@sv_fanbook_sign_all.on_fullmatch("全部签到", block=True)
async def calabiyau_fanbook_sign_all(bot: Bot, ev: Event) -> None:
    await bot.send("[卡丘] 开始全部签到任务，请稍后......", at_sender=bool(ev.group_id))
    reply = await run_all_fanbook_sign(ev)
    await bot.send(reply, at_sender=bool(ev.group_id))


@scheduler.scheduled_job(
    "cron",
    hour=_SIGN_HOUR,
    minute=_SIGN_MINUTE,
    id="klbq_fanbook_daily_sign",
    replace_existing=True,
)
async def scheduled_fanbook_daily_sign() -> None:
    await run_scheduled_fanbook_sign()


@on_core_start
async def on_start_fanbook_daily_sign() -> None:
    schedule_startup_fanbook_sign()
