"""卡拉彼丘兑换码数据拉取与文本格式化。"""

import re

from ..utils.api.biligame_wiki import WikiRedeemCodeItem, fetch_active_redeem_codes

_REWARD_SPLIT_RE = re.compile(r"[,，]\s*")
_EMPTY_REDEEM_CODES_TEXT = "暂时没有可用的兑换码喵~"


def format_redeem_rewards(raw_rewards: str) -> str:
    """将 Wiki 奖励内容字符串格式化为 `道具 x 数量` 列表。"""
    cleaned = raw_rewards.strip()
    if not cleaned:
        return "未知"

    formatted: list[str] = []
    for segment in _REWARD_SPLIT_RE.split(cleaned):
        part = segment.strip()
        if not part:
            continue
        if "*" in part:
            name, quantity = part.split("*", 1)
            item_name = name.strip()
            item_quantity = quantity.strip() or "1"
        else:
            item_name = part
            item_quantity = "1"
        if item_name:
            formatted.append(f"{item_name} x {item_quantity}")
    return ", ".join(formatted) if formatted else "未知"


def format_redeem_codes_text(items: list[WikiRedeemCodeItem]) -> str:
    """将未失效的兑换码条目列表格式化为回复文本。"""
    if not items:
        return _EMPTY_REDEEM_CODES_TEXT

    lines: list[str] = ["[卡拉彼丘兑换码]"]
    for item in items:
        expiry_text = "常驻" if item.is_permanent else item.expires_at.strftime("%Y-%m-%d %H:%M")
        rewards_text = format_redeem_rewards(item.rewards)
        lines.append(f"· 【{item.code}】有效期至：{expiry_text}")
        lines.append(f"    内含：{rewards_text}")
    return "\n".join(lines)


async def get_active_redeem_codes_text() -> str:
    """查询当前未失效兑换码并生成回复文案。"""
    items = await fetch_active_redeem_codes()
    return format_redeem_codes_text(items)
