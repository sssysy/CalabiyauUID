"""执行强制刷新并回复用户。"""

import time

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from ..utils.helper.refresh import refresh_player_data
from ..utils.api.dakanu.client import DakanuError
from ..utils.database.model_bind import get_main_uid
from ..utils.helper.player_resolve import resolve_player_input


async def resolve_refresh_uid(ev: Event) -> tuple[str, str | None]:
    raw_text = ev.text.strip()
    if raw_text:
        try:
            player_id = await resolve_player_input(raw_text)
        except DakanuError as exc:
            return "", str(exc)
        return player_id, None
    player_id = await get_main_uid(ev.bot_id, ev.user_id)
    if player_id is None:
        return "", "尚未绑定卡拉彼丘账号。\n发送 kq绑定 <UID 或昵称> 进行绑定。"
    return player_id, None


async def refresh_and_report(bot: Bot, ev: Event, player_id: str) -> None:
    try:
        result = await refresh_player_data(player_id, force=True)
    except DakanuError as exc:
        detail = str(exc)
        hint = "\n请检查 UID 是否正确；站点繁忙时可稍后重试。"
        if "没有找到" in detail:
            hint = "\n请确认 UID 是否正确后重试。"
        await bot.send([MessageSegment.at(ev.user_id), MessageSegment.text(f" 刷新失败：{detail}{hint}")])
        return
    except RuntimeError as exc:
        await bot.send([MessageSegment.at(ev.user_id), MessageSegment.text(f" 刷新失败：{exc}")])
        return
    saved_at = time.strftime("%Y-%m-%d %H:%M", time.localtime(result.snapshot.saved_at))
    await bot.send(
        [
            MessageSegment.at(ev.user_id),
            MessageSegment.text(f" UID {player_id} 战绩刷新成功。\n本地快照时间：{saved_at}"),
        ]
    )
