"""卡拉彼丘战队信息查询命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .clan_services import build_clan_card, resolve_clan_target
from ..utils.api.dakanu import DakanuError

sv_clan = SV("卡拉彼丘战队")


@sv_clan.on_command("战队", block=True)
async def calabiyau_clan_info(bot: Bot, ev: Event) -> None:
    clan, error = await resolve_clan_target(ev)
    if error is not None or clan is None:
        await bot.send(error or "未能解析目标战队。")
        return

    try:
        image = await build_clan_card(clan)
    except DakanuError as exc:
        logger.warning(f"[卡拉彼丘·战队查询] 读取战队 {clan['clanId']} 成员失败：{exc}")
        await bot.send(str(exc))
        return
    except RuntimeError:
        logger.exception(f"[卡拉彼丘·战队查询] 渲染战队 {clan['clanId']} 卡片失败")
        await bot.send("战队信息卡片生成失败，请稍后再试。")
        return

    await bot.send(image)
