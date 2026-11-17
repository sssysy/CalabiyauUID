"""卡拉彼丘封神榜命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .banned_services import build_banned_card
from ..utils.api.dakanu import DakanuError

sv_banned = SV("卡拉彼丘封神榜")


@sv_banned.on_command(
    "封神榜",
    block=True,
    to_ai="""查询卡拉彼丘封神榜最新封号名单或检索指定玩家封禁记录

    当用户想看最近封神榜名单，或查询某个玩家 UID/昵称是否被封号时调用。

    Args:
        text: 玩家纯数字 UID 或游戏昵称；留空则查询最新封神榜前 21 条记录，例如 "" 或 "1234567"
    """,
    covers=["卡拉彼丘封神榜最新封禁名单及按UID/昵称查询封号记录"],
    aliases=["卡拉彼丘·封号查询", "卡拉彼丘·反作弊名单"],
)
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
