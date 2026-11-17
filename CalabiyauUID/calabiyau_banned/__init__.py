"""卡拉彼丘封神榜命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .banned_services import build_banned_card
from ..utils.api.dakanu import DakanuError

sv_banned = SV("卡拉彼丘封神榜")


@sv_banned.on_command("封神榜", block=True)
async def calabiyau_banned(bot: Bot, ev: Event) -> None:
    query = ev.text.strip()
    try:
        image = await build_banned_card(query=query)
    except DakanuError as exc:
        await bot.send(str(exc))
        return
    except RuntimeError:
        logger.exception("[卡拉彼丘·封神榜] 渲染卡片失败")
        await bot.send("封神榜卡片生成失败，请稍后再试。")
        return
    await bot.send(image)
