"""卡拉彼丘进行中活动时间轴命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .activity_services import build_event_timeline_card
from ..utils.api.biligame_wiki import WikiError

sv_activity = SV("卡拉彼丘活动")


@sv_activity.on_fullmatch("活动", block=True)
async def calabiyau_event_timeline(bot: Bot, ev: Event) -> None:
    try:
        image = await build_event_timeline_card()
    except WikiError as exc:
        logger.warning(f"[卡拉彼丘·活动查询] 获取进行中活动失败：{exc}")
        await bot.send(str(exc))
        return
    except RuntimeError:
        logger.exception("[卡拉彼丘·活动查询] 渲染活动时间轴卡片失败")
        await bot.send("活动时间轴卡片生成失败，请稍后再试。")
        return
    await bot.send(image)
