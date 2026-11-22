"""Fanbook 自动签到汇总 HTML 卡片。"""

from dataclasses import dataclass

from ..render import CARD_WIDTH, CardTemplateContext, render_card


@dataclass(frozen=True)
class AutoSignFailureItem:
    """自动签到失败条目展示数据。"""

    label: str
    reason: str


@dataclass(frozen=True)
class AutoSignCardContext(CardTemplateContext):
    """自动签到汇总卡片模板上下文。"""

    sign_date: str = ""
    success_count: int = 0
    failed_count: int = 0
    failures: tuple[AutoSignFailureItem, ...] = ()


async def render_auto_sign_card(
    *,
    sign_date: str,
    success_count: int,
    failed_count: int,
    failures: tuple[AutoSignFailureItem, ...] = (),
) -> bytes:
    """渲染 Fanbook 自动签到群聊汇总卡片 PNG 字节。"""
    context = AutoSignCardContext(
        sign_date=sign_date,
        success_count=success_count,
        failed_count=failed_count,
        failures=failures,
    )
    return await render_card(
        "fanbook_auto_sign_card.html",
        context,
        width=CARD_WIDTH,
        default_font_size=24.0,
    )
