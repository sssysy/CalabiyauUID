"""卡拉彼丘极限推进榜命令与卡片构建。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .ranking_services import build_board_ranking_card
from ..utils.api.dakanu import DakanuError


async def build_pushcar_ranking_card(*, use_cache: bool = True) -> bytes:
    """拉取前 50 名极限推进榜并渲染卡片。"""
    return await build_board_ranking_card(rank_type=6, include_floor=False, use_cache=use_cache)


def register_pushcar_ranking(sv_ranking: SV) -> None:
    """向排行服务注册推进排行命令。"""

    @sv_ranking.on_fullmatch("推进排行", block=True)
    async def calabiyau_pushcar_ranking(bot: Bot, ev: Event) -> None:
        try:
            image = await build_pushcar_ranking_card()
        except DakanuError as exc:
            await bot.send(str(exc))
            return
        except RuntimeError:
            logger.exception("[卡拉彼丘·推进排行] 渲染卡片失败")
            await bot.send("推进排行卡片生成失败，请稍后再试。")
            return
        await bot.send(image)
