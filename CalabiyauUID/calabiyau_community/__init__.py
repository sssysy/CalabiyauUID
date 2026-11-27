"""卡拉彼丘玩家活跃与世界频道动态命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .community_services import build_activity_card, build_world_chat_card
from ..utils.api.dakanu.client import DakanuError

sv_activity = SV("卡拉彼丘活跃")

_RANGE_PARAM_MAP: dict[str, str] = {
    "6h": "6h",
    "24h": "24h",
    "7d": "7d",
    "30d": "30d",
    "6小时": "6h",
    "24小时": "24h",
    "7天": "7d",
    "30天": "30d",
}


@sv_activity.on_regex(
    r"^活跃图(?P<range>6h|24h|7d|30d|6小时|24小时|7天|30天)?$",
    block=True,
    to_ai="""查询卡拉彼丘玩家活跃趋势曲线卡片与日活估算

    当用户询问卡拉彼丘当前在线人数、日活、玩家活跃度趋势或近几天在线波动时调用。

    Args:
        text: 必须完整匹配格式 "活跃图[周期]"，可选周期为 6h/24h/7d/30d/6小时/24小时/7天/30天，例如：
              - "活跃图24h"
              - "活跃图7d"
              - "活跃图30d"
              - "活跃图"
    """,
    covers=["卡拉彼丘玩家在线活跃趋势曲线、日活与30日活跃估算"],
    aliases=["卡拉彼丘·活跃趋势", "卡拉彼丘·在线人数"],
)
async def calabiyau_activity_trend(bot: Bot, ev: Event) -> None:
    raw_range = ev.regex_dict["range"] if "range" in ev.regex_dict else None
    range_key = _RANGE_PARAM_MAP[raw_range] if raw_range in _RANGE_PARAM_MAP else "24h"
    try:
        image = await build_activity_card(range_key=range_key)
    except DakanuError as exc:
        logger.warning(f"[卡拉彼丘·活跃趋势] 获取玩家活跃数据失败：{exc}")
        await bot.send(str(exc))
        return
    except RuntimeError:
        logger.exception("[卡拉彼丘·活跃趋势] 渲染卡片失败")
        await bot.send("玩家活跃趋势卡片生成失败，请稍后再试。")
        return
    await bot.send(image)


@sv_activity.on_fullmatch(
    ("世界聊天", "世界频道"),
    block=True,
    to_ai="""查询卡拉彼丘游戏内世界频道实时聊天动态

    当用户想看当前卡拉彼丘世界频道大家在聊什么、实时公屏动态时调用。

    Args:
        text: 无需参数，留空即可
    """,
    covers=["卡拉彼丘游戏世界频道实时公屏聊天动态"],
    aliases=["卡拉彼丘·世界频道动态", "卡拉彼丘·公屏聊天"],
)
async def calabiyau_world_chat(bot: Bot, ev: Event) -> None:
    try:
        image = await build_world_chat_card()
    except DakanuError as exc:
        logger.warning(f"[卡拉彼丘·世界聊天] 获取世界频道动态失败：{exc}")
        await bot.send(str(exc))
        return
    except RuntimeError:
        logger.exception("[卡拉彼丘·世界聊天] 渲染卡片失败")
        await bot.send("世界频道动态卡片生成失败，请稍后再试。")
        return
    await bot.send(image)
