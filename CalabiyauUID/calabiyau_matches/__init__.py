"""卡拉彼丘历史战绩命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .matches_services import resolve_match_player_id, build_recent_matches_card
from ..utils.api.dakanu import DakanuError

sv_matches = SV("卡拉彼丘历史战绩")


@sv_matches.on_fullmatch(
    "历史战绩",
    block=True,
    to_ai="""查询当前绑定卡拉彼丘账号的最近 8 场历史战绩卡片与对局列表

    当用户想看最近几把打了什么、近期胜负、最近对局 KDA/地图/角色或获取对局 roomId 时调用。
    此工具仅查询当前绑定主账号，不支持传入他人 UID。

    Args:
        text: 无需参数，留空即可
    """,
    covers=["卡拉彼丘当前账号最近8场对局记录卡片、地图角色战绩与roomId"],
    aliases=["卡拉彼丘·最近战绩", "卡拉彼丘·对局记录"],
)
async def calabiyau_recent_matches(bot: Bot, ev: Event) -> None:
    player_id, error = await resolve_match_player_id(ev)
    if error is not None:
        await bot.send(error)
        return
    try:
        image = await build_recent_matches_card(player_id)
    except DakanuError as exc:
        await bot.send(str(exc))
        return
    except RuntimeError:
        logger.exception("[卡拉彼丘·历史战绩] 渲染卡片失败")
        await bot.send("历史战绩卡片生成失败，请稍后再试。")
        return
    await bot.send(image)
