"""卡拉彼丘排行榜命令。"""

from collections.abc import Awaitable

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .ranking_services import (
    RolesSortBy,
    resolve_role_query,
    build_board_ranking_card,
    build_roles_ranking_card,
    build_role_board_usage_message,
)
from ..utils.api.dakanu import DakanuError

sv_ranking = SV("卡拉彼丘排行")


async def _send_ranking_card(
    bot: Bot,
    card_coro: Awaitable[bytes],
    *,
    log_prefix: str,
    board_name: str,
    log_api_error: bool = False,
) -> None:
    try:
        image = await card_coro
    except DakanuError as exc:
        if log_api_error:
            logger.warning(f"{log_prefix} 获取{board_name}失败：{exc}")
        await bot.send(str(exc))
        return
    except RuntimeError:
        logger.exception(f"{log_prefix} 渲染卡片失败")
        await bot.send(f"{board_name}卡片生成失败，请稍后再试。")
        return
    await bot.send(image)


@sv_ranking.on_fullmatch(
    "排位排行",
    block=True,
    to_ai="""查询卡拉彼丘当前赛季排位段位排行榜

    当用户想看卡拉彼丘排位榜、国服高分段榜单、排位前50名或上榜门槛分数时调用。

    Args:
        text: 无需参数，留空即可
    """,
    covers=["卡拉彼丘排位赛段位排行榜前50名与上榜门槛分数"],
    aliases=["卡拉彼丘·排位榜", "卡拉彼丘·段位排行榜"],
)
async def calabiyau_ranking(bot: Bot, ev: Event) -> None:
    await _send_ranking_card(
        bot,
        build_board_ranking_card(rank_type=1, include_floor=True),
        log_prefix="[卡拉彼丘·排位排行]",
        board_name="排位排行",
    )


@sv_ranking.on_fullmatch(
    ("团队排行", "团竞排行", "团队乱斗排行", "团队竞技排行", "乱斗排行"),
    block=True,
    to_ai="""查询卡拉彼丘团队乱斗排行榜

    当用户想看团队乱斗/团队竞技/团竞模式玩家排行榜时调用。

    Args:
        text: 无需参数，留空即可
    """,
    covers=["卡拉彼丘团队乱斗模式玩家排行榜"],
    aliases=["卡拉彼丘·团竞榜", "卡拉彼丘·团队乱斗排行"],
)
async def calabiyau_team_ranking(bot: Bot, ev: Event) -> None:
    await _send_ranking_card(
        bot,
        build_board_ranking_card(rank_type=2, include_floor=False),
        log_prefix="[卡拉彼丘·团队排行]",
        board_name="团队排行",
    )


@sv_ranking.on_fullmatch(
    ("推进排行", "推车排行", "极限推进排行"),
    block=True,
    to_ai="""查询卡拉彼丘极限推进排行榜

    当用户想看极限推进/推车模式玩家排行榜时调用。

    Args:
        text: 无需参数，留空即可
    """,
    covers=["卡拉彼丘极限推进推车模式玩家排行榜"],
    aliases=["卡拉彼丘·推车榜", "卡拉彼丘·极限推进排行"],
)
async def calabiyau_pushcar_ranking(bot: Bot, ev: Event) -> None:
    await _send_ranking_card(
        bot,
        build_board_ranking_card(rank_type=6, include_floor=False),
        log_prefix="[卡拉彼丘·推进排行]",
        board_name="推进排行",
    )


@sv_ranking.on_fullmatch(
    ("挑战排行", "匹配排行", "娱乐排行"),
    block=True,
    to_ai="""查询卡拉彼丘挑战模式排行榜

    当用户想看挑战/匹配/娱乐模式玩家段位排行榜时调用。

    Args:
        text: 无需参数，留空即可
    """,
    covers=["卡拉彼丘挑战/娱乐模式玩家排行榜"],
    aliases=["卡拉彼丘·挑战榜", "卡拉彼丘·娱乐排行"],
)
async def calabiyau_challenge_ranking(bot: Bot, ev: Event) -> None:
    await _send_ranking_card(
        bot,
        build_board_ranking_card(rank_type=7, include_floor=False),
        log_prefix="[卡拉彼丘·挑战排行]",
        board_name="挑战排行",
    )


@sv_ranking.on_fullmatch(
    ("感染排行", "生化排行", "晶源感染排行"),
    block=True,
    to_ai="""查询卡拉彼丘晶源感染排行榜

    当用户想看晶源感染/生化模式玩家排行榜时调用。

    Args:
        text: 无需参数，留空即可
    """,
    covers=["卡拉彼丘晶源感染生化模式玩家排行榜"],
    aliases=["卡拉彼丘·感染榜", "卡拉彼丘·生化排行"],
)
async def calabiyau_infection_ranking(bot: Bot, ev: Event) -> None:
    await _send_ranking_card(
        bot,
        build_board_ranking_card(rank_type=8, include_floor=False),
        log_prefix="[卡拉彼丘·感染排行]",
        board_name="感染排行",
    )


@sv_ranking.on_command(
    "超弦体排行",
    block=True,
    to_ai="""查询指定卡拉彼丘超弦体角色的玩家战力排行榜

    当用户想看某个特定角色/超弦体（如星绘、米雪儿、令、香奈美等）的玩家单榜排行时调用。

    Args:
        text: 超弦体正式名称、常用别名、拼音或角色 ID，例如 "星绘"、"糖猫"、"146"
    """,
    covers=["卡拉彼丘单个超弦体角色的玩家榜单排行"],
    aliases=["卡拉彼丘·角色战力榜", "卡拉彼丘·绝活榜"],
)
async def calabiyau_role_board_ranking(bot: Bot, ev: Event) -> None:
    query = ev.text.strip()
    if not query:
        await bot.send(await build_role_board_usage_message())
        return

    try:
        resolved = await resolve_role_query(query)
    except DakanuError as exc:
        logger.warning(f"[卡拉彼丘·超弦体排行] 解析角色参数失败：{exc}")
        await bot.send(str(exc))
        return

    if resolved is None:
        await bot.send(await build_role_board_usage_message())
        return

    role_id, role_name = resolved
    await _send_ranking_card(
        bot,
        build_board_ranking_card(
            rank_type=4,
            sub_type=role_id,
            title_override=f"角色榜 · {role_name}",
            include_floor=False,
        ),
        log_prefix="[卡拉彼丘·超弦体排行]",
        board_name="超弦体排行",
        log_api_error=True,
    )


@sv_ranking.on_regex(
    r"^角色(?P<scope>排位|全部)?(?P<metric>出场率|胜率)?排行$",
    block=True,
    to_ai="""查询卡拉彼丘全超弦体胜率与出场率统计榜

    当用户想看当前版本各角色/超弦体的胜率榜、出场率榜、强度梯队或排位/全模式统计时调用。

    Args:
        text: 必须完整匹配格式 "角色[排位|全部][出场率|胜率]排行"，例如：
              - "角色排位胜率排行"
              - "角色排位出场率排行"
              - "角色全部胜率排行"
              - "角色排行"
    """,
    covers=["卡拉彼丘全超弦体排位与全模式胜率、出场率统计榜"],
    aliases=["卡拉彼丘·角色胜率榜", "卡拉彼丘·角色出场率榜"],
)
async def calabiyau_roles_ranking(bot: Bot, ev: Event) -> None:
    scope = ev.regex_dict["scope"] if "scope" in ev.regex_dict else None
    metric = ev.regex_dict["metric"] if "metric" in ev.regex_dict else None
    ranked_only = scope != "全部"
    sort_by: RolesSortBy = "appearanceRate" if metric == "出场率" else "winRate"
    await _send_ranking_card(
        bot,
        build_roles_ranking_card(sort_by=sort_by, ranked_only=ranked_only),
        log_prefix="[卡拉彼丘·角色排行]",
        board_name="角色排行",
        log_api_error=True,
    )
