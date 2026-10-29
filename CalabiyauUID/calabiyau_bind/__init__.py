"""卡拉彼丘账号绑定命令。"""

import asyncio

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from .bind_services import bind_account, view_accounts, unbind_account
from ..utils.api.dakanu import DakanuError
from ..utils.helper.refresh import track_background

sv_bind = SV("卡拉彼丘账号绑定")


@sv_bind.on_command("绑定", block=True)
async def calabiyau_bind(bot: Bot, ev: Event) -> None:
    game_uid = ev.text.strip()
    if not game_uid.isdigit():
        await bot.send("请在命令后附带卡拉彼丘 UID。\n例如：kq绑定 1234567")
        return

    await bot.send("已开始验证 UID 并拉取首次战绩，通常需要 10～30 秒。\n完成后会在这个会话提醒你。")
    task = asyncio.create_task(_bind_and_notify(bot, ev, game_uid))
    track_background(task)


async def _bind_and_notify(bot: Bot, ev: Event, game_uid: str) -> None:
    try:
        message = await bind_account(ev.bot_id, ev.user_id, game_uid)
    except DakanuError as exc:
        detail = str(exc)
        hint = "\n请检查 UID 是否正确；站点繁忙时可稍后重试。"
        if "没有找到" in detail:
            hint = "\n请确认 UID 是否正确后重试。"
        await bot.send([MessageSegment.at(ev.user_id), MessageSegment.text(f" 绑定失败：{detail}{hint}")])
        return
    except RuntimeError as exc:
        await bot.send([MessageSegment.at(ev.user_id), MessageSegment.text(f" 绑定失败：{exc}")])
        return
    await bot.send([MessageSegment.at(ev.user_id), MessageSegment.text(f" {message}")])


@sv_bind.on_command("解绑", block=True)
async def calabiyau_unbind(bot: Bot, ev: Event) -> None:
    game_uid = ev.text.strip()
    if not game_uid.isdigit():
        await bot.send("请在命令后附带卡拉彼丘 UID。\n例如：kq解绑 1234567")
        return

    await bot.send(await unbind_account(ev.bot_id, ev.user_id, game_uid))


@sv_bind.on_fullmatch("查看", block=True)
async def calabiyau_view(bot: Bot, ev: Event) -> None:
    await bot.send(await view_accounts(ev.bot_id, ev.user_id))
