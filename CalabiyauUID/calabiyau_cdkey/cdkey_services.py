"""卡拉彼丘兑换码数据拉取与文本格式化。"""

from ..utils.api.biligame_wiki import WikiRedeemCodeItem, fetch_active_redeem_codes
from ..utils.helper.cdkey_remind import format_redeem_rewards

_EMPTY_REDEEM_CODES_TEXT = "暂时没有可用的兑换码喵~"


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
