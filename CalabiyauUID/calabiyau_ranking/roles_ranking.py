"""角色胜率与出场率排行数据拉取、命令解析与卡片渲染。"""

import time
import asyncio
from dataclasses import dataclass

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .ranking_services import load_ranking_role_images
from ..utils.api.dakanu import DakanuError, fetch_meta_roles, fetch_roles_ranking
from ..utils.helper.maps import get_role_display_names
from ..utils.render.html.roles_ranking_card import render_roles_ranking_card

_CACHE_TTL_SECONDS = 30.0
_DOWNLOAD_CONCURRENCY = 8
_ROLES_RANKING_PATTERN = r"^角色(?P<scope>排位|全部)?(?P<metric>出场率|胜率)?排行$"


@dataclass(frozen=True)
class _RolesRankingCardCache:
    expires_at: float
    image: bytes


_cache_lock = asyncio.Lock()
_cached_cards: dict[tuple[str, bool], _RolesRankingCardCache] = {}


async def build_roles_ranking_card(
    *,
    sort_by: str = "winRate",
    ranked_only: bool = True,
    use_cache: bool = True,
) -> bytes:
    """拉取角色胜率与出场率排行并渲染卡片，带 30 秒短时内存缓存。"""
    if sort_by not in {"appearanceRate", "winRate"}:
        raise ValueError(f"不支持的排序字段：{sort_by}")
    cache_key = (sort_by, ranked_only)
    async with _cache_lock:
        now = time.monotonic()
        if use_cache and cache_key in _cached_cards and now < _cached_cards[cache_key].expires_at:
            return _cached_cards[cache_key].image

        board, remote_roles = await asyncio.gather(
            fetch_roles_ranking(ranked_only=ranked_only),
            fetch_meta_roles(),
        )
        role_names = {**remote_roles, **get_role_display_names()}
        role_ids = {entry["roleId"] for entry in board["entries"]}
        role_images = await load_ranking_role_images(
            role_ids,
            asyncio.Semaphore(_DOWNLOAD_CONCURRENCY),
        )
        image = await render_roles_ranking_card(
            board,
            role_names,
            role_images,
            sort_by=sort_by,
        )
        _cached_cards[cache_key] = _RolesRankingCardCache(
            expires_at=time.monotonic() + _CACHE_TTL_SECONDS,
            image=image,
        )
        return image


def register_roles_ranking(sv_ranking: SV) -> None:
    """向排行服务注册角色胜率与出场率排行命令。"""

    @sv_ranking.on_regex(_ROLES_RANKING_PATTERN, block=True)
    async def calabiyau_roles_ranking(bot: Bot, ev: Event) -> None:
        scope = ev.regex_dict["scope"] if "scope" in ev.regex_dict else None
        metric = ev.regex_dict["metric"] if "metric" in ev.regex_dict else None
        ranked_only = scope != "全部"
        sort_by = "appearanceRate" if metric == "出场率" else "winRate"
        try:
            image = await build_roles_ranking_card(sort_by=sort_by, ranked_only=ranked_only)
        except DakanuError as exc:
            logger.warning(f"[卡拉彼丘·角色排行] 获取角色排行失败：{exc}")
            await bot.send(str(exc))
            return
        except RuntimeError:
            logger.exception("[卡拉彼丘·角色排行] 渲染卡片失败")
            await bot.send("角色排行卡片生成失败，请稍后再试。")
            return
        await bot.send(image)
