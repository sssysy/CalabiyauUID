"""卡拉彼丘兑换码查询命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .cdkey_services import get_active_redeem_codes_text
from ..utils.api.biligame_wiki import WikiError

sv_cdkey = SV("卡拉彼丘兑换码")


@sv_cdkey.on_fullmatch("兑换码", block=True)
async def calabiyau_redeem_codes(bot: Bot, ev: Event) -> None:
    try:
        reply = await get_active_redeem_codes_text()
    except WikiError as exc:
        logger.warning(f"[卡拉彼丘·兑换码] 获取兑换码失败：{exc}")
        await bot.send(str(exc))
        return
    await bot.send(reply)
