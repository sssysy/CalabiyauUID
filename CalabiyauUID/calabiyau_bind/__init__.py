"""卡拉彼丘账号绑定命令。"""

import asyncio

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from .bind_services import bind_account, view_accounts, switch_account, unbind_account_by_query
from ..utils.api.dakanu import DakanuError
from ..utils.utils.background import track_background_task
from ..utils.helper.player_resolve import resolve_player_input

sv_bind = SV("卡拉彼丘账号绑定")


@sv_bind.on_command(
    "绑定",
    block=True,
    to_ai="""绑定卡拉彼丘国服账号并拉取首次战绩快照

    当用户要求绑定卡拉彼丘账号、关联游戏UID或游戏昵称时调用。
    调用后会验证账号并拉取首次战绩，完成后即可查询战绩总览或历史战绩。

    Args:
        text: 卡拉彼丘纯数字 UID 或游戏昵称，例如 "1234567" 或 "星绘玩家"
    """,
    covers=["卡拉彼丘国服账号绑定、UID/昵称解析及首次战绩快照拉取"],
    aliases=["卡拉彼丘·绑定账号", "卡拉彼丘·绑定UID"],
    timeout=120.0,
    background=True,
    background_grace=5.0,
)
async def calabiyau_bind(bot: Bot, ev: Event) -> None:
    query = ev.text.strip()
    if not query:
        await bot.send("请在命令后附带卡拉彼丘 UID 或游戏昵称。\n例如：kq绑定 1234567")
        return

    try:
        game_uid = await resolve_player_input(query)
    except DakanuError as exc:
        await bot.send(f"绑定失败：{exc}")
        return

    if type(bot).__name__ == "MockBot":
        await _bind_and_notify(bot, ev, game_uid)
        return

    await bot.send(f"已开始验证 UID {game_uid} 并拉取首次战绩，通常需要 10～30 秒。\n完成后会在这个会话提醒你。")
    task = asyncio.create_task(_bind_and_notify(bot, ev, game_uid))
    track_background_task(task)


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


@sv_bind.on_command(
    ("解绑", "解除绑定"),
    block=True,
    to_ai="""解绑已绑定的卡拉彼丘账号

    当用户明确要求解除绑定某个卡拉彼丘 UID 或昵称时调用。

    Args:
        text: 要解绑的卡拉彼丘 UID 或已绑定账号的游戏昵称，例如 "1234567"
    """,
    covers=["卡拉彼丘已绑定账号解绑"],
    aliases=["卡拉彼丘·解绑账号", "卡拉彼丘·解除绑定"],
)
async def calabiyau_unbind(bot: Bot, ev: Event) -> None:
    query = ev.text.strip()
    if not query:
        await bot.send("请在命令后附带卡拉彼丘 UID 或游戏昵称。\n例如：kq解绑 1234567")
        return

    await bot.send(await unbind_account_by_query(ev.bot_id, ev.user_id, query))


@sv_bind.on_fullmatch(
    "查看",
    block=True,
    to_ai="""查看当前用户已绑定的卡拉彼丘账号列表

    当用户询问自己绑定了哪些卡拉彼丘账号、当前主账号是哪个时调用。

    Args:
        text: 无需参数，留空即可
    """,
    covers=["卡拉彼丘当前用户已绑定账号列表与主账号查询"],
    aliases=["卡拉彼丘·查看绑定", "卡拉彼丘·我的账号"],
)
async def calabiyau_view(bot: Bot, ev: Event) -> None:
    await bot.send(await view_accounts(ev.bot_id, ev.user_id))


@sv_bind.on_command(
    "切换",
    block=True,
    to_ai="""切换当前使用的卡拉彼丘主账号

    当用户想更换当前默认查询的卡拉彼丘账号时调用。

    Args:
        text: 目标账号的 UID 或昵称；留空时默认切换到下一个已绑定账号，例如 "" 或 "1234567"
    """,
    covers=["卡拉彼丘已绑定主账号切换"],
    aliases=["卡拉彼丘·切换账号"],
)
async def calabiyau_switch(bot: Bot, ev: Event) -> None:
    await bot.send(await switch_account(ev.bot_id, ev.user_id, ev.text.strip()))
