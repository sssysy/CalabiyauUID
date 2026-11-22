"""卡拉彼丘表情包随机抽取命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .sticker_services import get_random_sticker, parse_sticker_query

sv_sticker = SV("卡拉彼丘表情包")


@sv_sticker.on_command(("抽表情", "表情包"), block=True)
async def calabiyau_random_sticker(bot: Bot, ev: Event) -> None:
    query, parse_error = parse_sticker_query(ev.text)
    if parse_error is not None:
        await bot.send(parse_error)
        return

    result = await get_random_sticker(query)
    if result.error is not None or result.image is None:
        await bot.send(result.error or "获取表情包失败，请稍后再试。")
        return
    await bot.send(result.image)
