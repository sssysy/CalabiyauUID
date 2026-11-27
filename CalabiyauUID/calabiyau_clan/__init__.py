"""卡拉彼丘战队信息查询命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .clan_services import (
    build_clan_card,
    build_clan_card_from_snapshot,
    resolve_clan_target_with_refresh,
)
from ..utils.helper.refresh import (
    BUSY_FALLBACK_NOTICE,
    schedule_refreshed_card_push,
)
from ..utils.api.dakanu.client import DakanuError

sv_clan = SV("卡拉彼丘战队")


@sv_clan.on_command(
    "战队查询",
    block=True,
    to_ai="""查询卡拉彼丘战队信息与成员列表卡片

    当用户想查某个战队名称/ID，或查询自己/@的用户当前所在战队的资料与成员时调用。

    Args:
        text: 战队名称或纯数字战队 ID；留空则查询当前绑定账号（或被@用户）所在战队，例如 "" 或 "某战队"
    """,
    covers=["卡拉彼丘战队资料、等级人数、简介及成员列表查询"],
    aliases=["卡拉彼丘·查战队", "卡拉彼丘·战队信息"],
    timeout=120.0,
    background=True,
    background_grace=5.0,
)
async def calabiyau_clan_info(bot: Bot, ev: Event) -> None:
    resolved = await resolve_clan_target_with_refresh(
        ev,
        allow_stale_fallback=type(bot).__name__ != "MockBot",
    )
    if resolved.error is not None or resolved.clan is None:
        await bot.send(resolved.error or "未能解析目标战队。")
        return
    clan = resolved.clan

    try:
        image = await build_clan_card(clan)
    except DakanuError as exc:
        logger.warning(f"[卡拉彼丘·战队查询] 读取战队 {clan.clanId} 成员失败：{exc}")
        await bot.send(str(exc))
        return
    except RuntimeError:
        logger.exception(f"[卡拉彼丘·战队查询] 渲染战队 {clan.clanId} 卡片失败")
        await bot.send("战队信息卡片生成失败，请稍后再试。")
        return

    if resolved.pending_task is not None and resolved.player_id is not None:
        await bot.send(BUSY_FALLBACK_NOTICE)
        await bot.send(image)
        schedule_refreshed_card_push(
            bot,
            resolved.pending_task,
            build_clan_card_from_snapshot,
            feature_name="战队查询",
            player_id=resolved.player_id,
        )
        return

    await bot.send(image)
