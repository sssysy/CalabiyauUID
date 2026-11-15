"""卡拉彼丘排位排行命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .ranking_services import build_ranking_card
from ..utils.api.dakanu import DakanuError

sv_ranking = SV("卡拉彼丘排行")


@sv_ranking.on_fullmatch("排位排行", block=True)
async def calabiyau_ranking(bot: Bot, ev: Event) -> None:
    try:
        image = await build_ranking_card()
    except DakanuError as exc:
        await bot.send(str(exc))
        return
    except RuntimeError:
        logger.exception("[卡拉彼丘·排位排行] 渲染卡片失败")
        await bot.send("排位排行卡片生成失败，请稍后再试。")
        return
    await bot.send(image)
