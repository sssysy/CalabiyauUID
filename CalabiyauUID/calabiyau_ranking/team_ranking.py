"""卡拉彼丘团队乱斗榜命令与卡片构建。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .ranking_services import build_board_ranking_card
from ..utils.api.dakanu import DakanuError


async def build_team_ranking_card(*, use_cache: bool = True) -> bytes:
    """拉取前 50 名团队乱斗榜并渲染卡片。"""
    return await build_board_ranking_card(rank_type=2, include_floor=False, use_cache=use_cache)


def register_team_ranking(sv_ranking: SV) -> None:
    """向排行服务注册团队排行命令。"""

    @sv_ranking.on_fullmatch("团队排行", block=True)
    async def calabiyau_team_ranking(bot: Bot, ev: Event) -> None:
        try:
            image = await build_team_ranking_card()
        except DakanuError as exc:
            await bot.send(str(exc))
            return
        except RuntimeError:
            logger.exception("[卡拉彼丘·团队排行] 渲染卡片失败")
            await bot.send("团队排行卡片生成失败，请稍后再试。")
            return
        await bot.send(image)
