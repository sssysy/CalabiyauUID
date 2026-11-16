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
from ..utils.api.dakanu import DakanuError

sv_replay = SV("卡拉彼丘回放下载")


@sv_replay.on_command(("回放下载", "下载回放", "下载录像"), block=True)
async def calabiyau_replay_download(bot: Bot, ev: Event) -> None:
    room_id = parse_room_id(ev.text)
    if room_id is None:
        await bot.send("请在命令后附带正确的对局 ID。\n例如：kq回放下载 123456789012345678")
        return

    replay_path = await get_cached_replay(room_id)
    if replay_path is None:
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

    await bot.send(file_msg)
