"""晶源感染榜命令与渲染入口。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .ranking_services import build_board_ranking_card
from ..utils.api.dakanu import DakanuError


async def build_infection_ranking_card(*, use_cache: bool = True) -> bytes:
    """拉取前 50 名晶源感染榜并渲染卡片。"""
    return await build_board_ranking_card(
        rank_type=8,
        include_floor=False,
        use_cache=use_cache,
    )


def register_infection_ranking(sv_ranking: SV) -> None:
    """注册晶源感染榜命令。"""

    @sv_ranking.on_fullmatch("感染排行", block=True)
    async def calabiyau_infection_ranking(bot: Bot, ev: Event) -> None:
        try:
            image = await build_infection_ranking_card()
        except DakanuError as exc:
            await bot.send(str(exc))
            return
        except RuntimeError:
            logger.exception("[卡拉彼丘·感染排行] 渲染卡片失败")
            await bot.send("感染排行卡片生成失败，请稍后再试。")
            return
        await bot.send(image)
