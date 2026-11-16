"""卡拉彼丘插件帮助命令与全局帮助注册。"""

from gsuid_core.sv import SV, get_plugin_available_prefix
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.server import on_core_start
from gsuid_core.help.utils import register_help

from .help_services import (
    load_plugin_icon,
    get_calabiyau_help,
    ensure_help_textures,
    start_steam_background_sync,
)

sv_help = SV("卡拉彼丘帮助")

# 必须先完成默认底图复制与模糊生成，再注册全局帮助
ensure_help_textures()
register_help(
    "CalabiyauUID",
    f"{get_plugin_available_prefix('CalabiyauUID')}帮助",
    load_plugin_icon(),
)


@sv_help.on_fullmatch("帮助", block=True)
async def calabiyau_help(bot: Bot, ev: Event) -> None:
    logger.info("[卡拉彼丘·帮助] 开始生成帮助图")
    image = await get_calabiyau_help(ev.user_pm)
    await bot.send(image)


@on_core_start
async def schedule_steam_help_bg_sync() -> None:
    start_steam_background_sync()
