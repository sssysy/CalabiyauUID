"""卡拉彼丘对局回放下载命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .replay_services import (
    parse_room_id,
    get_cached_replay,
    ensure_replay_file,
    build_replay_file_message,
)
from ..utils.helper.ai_bridge import emit_ai_text
from ..utils.api.dakanu.client import DakanuError

sv_replay = SV("卡拉彼丘回放下载")


@sv_replay.on_command(
    ("回放下载", "下载回放", "下载录像"),
    block=True,
    to_ai="""下载指定卡拉彼丘对局 ID（roomId）的录像回放文件

    当用户要求下载某一场卡拉彼丘对局的录像/回放文件时调用。
    对局 ID 可从历史战绩摘要的 roomId 获取。

    Args:
        text: 纯数字对局 roomId，例如 "123456789012345678"
    """,
    covers=["卡拉彼丘指定对局roomId的录像回放文件下载"],
    aliases=["卡拉彼丘·下载回放", "卡拉彼丘·下载录像"],
    timeout=180.0,
    background=True,
    background_grace=5.0,
)
async def calabiyau_replay_download(bot: Bot, ev: Event) -> None:
    room_id = parse_room_id(ev.text)
    if room_id is None:
        await bot.send("请在命令后附带正确的对局 ID。\n例如：kq回放下载 123456789012345678")
        return

    replay_path = await get_cached_replay(room_id)
    if replay_path is None:
        if type(bot).__name__ != "MockBot":
            await bot.send(f"正在下载对局 {room_id} 的回放文件，请稍候...")
        try:
            replay_path = await ensure_replay_file(room_id)
        except DakanuError as exc:
            await bot.send(str(exc))
            return

    try:
        file_msg = await build_replay_file_message(replay_path)
    except OSError:
        logger.exception(f"[卡拉彼丘·回放下载] 读取回放文件失败：{replay_path}")
        await bot.send("读取本地回放文件失败，请稍后再试。")
        return

    emit_ai_text(f"已获取对局 {room_id} 回放文件：{replay_path.name}")
    await bot.send(file_msg)
