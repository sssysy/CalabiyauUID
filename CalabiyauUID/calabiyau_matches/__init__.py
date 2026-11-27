"""卡拉彼丘历史战绩命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .matches_services import (
    resolve_match_player_id,
    build_recent_matches_card_from_snapshot,
)
from ..utils.helper.refresh import (
    BUSY_FALLBACK_NOTICE,
    schedule_refreshed_card_push,
    ensure_player_snapshot_with_fallback,
)
from .match_analysis_services import parse_analysis_room_id, build_match_analysis_card
from ..utils.api.dakanu.client import DakanuError

sv_matches = SV("卡拉彼丘历史战绩")


@sv_matches.on_fullmatch(
    "历史战绩",
    block=True,
)
async def calabiyau_recent_matches(bot: Bot, ev: Event) -> None:
    player_id, error = await resolve_match_player_id(ev)
    if error is not None:
        await bot.send(error)
        return
    try:
        fetched = await ensure_player_snapshot_with_fallback(player_id)
        image = await build_recent_matches_card_from_snapshot(fetched.snapshot)
    except DakanuError as exc:
        await bot.send(str(exc))
        return
    except RuntimeError:
        logger.exception("[卡拉彼丘·历史战绩] 渲染卡片失败")
        await bot.send("历史战绩卡片生成失败，请稍后再试。")
        return
    if fetched.pending_task is not None:
        await bot.send(BUSY_FALLBACK_NOTICE)
        await bot.send(image)
        schedule_refreshed_card_push(
            bot,
            fetched.pending_task,
            build_recent_matches_card_from_snapshot,
            feature_name="历史战绩",
            player_id=player_id,
        )
        return
    await bot.send(image)


@sv_matches.on_command("对局分析", block=True)
async def calabiyau_match_analysis(bot: Bot, ev: Event) -> None:
    room_id = parse_analysis_room_id(ev.text)
    if room_id is None:
        await bot.send("请在命令后附带正确的对局 ID。\n例如：kq对局分析 123456789012345678")
        return
    await bot.send("正在拉取该对战数据，请耐心等待")
    try:
        image = await build_match_analysis_card(room_id)
    except DakanuError as exc:
        await bot.send(str(exc))
        return
    except RuntimeError:
        logger.exception(f"[卡拉彼丘·对局分析] 渲染对局 {room_id} 分析卡片失败")
        await bot.send("对局分析卡片生成失败，请稍后再试。")
        return
    await bot.send(image)
