"""卡拉彼丘数据刷新命令。"""

import asyncio

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .refresh_services import refresh_and_report, resolve_refresh_uid
from ..utils.helper.refresh import track_background

sv_refresh = SV("卡拉彼丘数据刷新")


@sv_refresh.on_command(
    ("刷新数据", "更新数据"),
    block=True,
    to_ai="""刷新卡拉彼丘玩家的最新战绩快照

    当用户明确要求更新或刷新卡拉彼丘战绩数据，或本地快照缺失/过期需要拉取最新数据时调用。
    调用后会向战绩站发起刷新并拉取最新快照，完成后返回最新快照时间。

    Args:
        text: 目标玩家的 UID 或游戏昵称；留空则刷新当前用户绑定的主账号，例如 "" 或 "1234567"
    """,
    covers=["卡拉彼丘玩家战绩强制刷新与本地快照更新"],
    aliases=["卡拉彼丘·刷新战绩", "卡拉彼丘·更新数据"],
    timeout=120.0,
    background=True,
    background_grace=5.0,
)
async def calabiyau_refresh_data(bot: Bot, ev: Event) -> None:
    player_id, error = await resolve_refresh_uid(ev)
    if error is not None:
        await bot.send(error)
        return
    if type(bot).__name__ == "MockBot":
        await refresh_and_report(bot, ev, player_id)
        return
    await bot.send(f"已开始刷新 UID {player_id} 的战绩，通常需要 10～30 秒。\n完成后会在这个会话提醒你。")
    task = asyncio.create_task(refresh_and_report(bot, ev, player_id))
    track_background(task)
