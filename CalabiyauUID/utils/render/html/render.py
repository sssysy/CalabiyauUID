"""HTML 卡片模板加载与统一 pytakumi 渲染入口。"""

from pathlib import Path
from dataclasses import dataclass

import jinja2

from gsuid_core.utils.html_render import render_html_to_bytes

CARD_WIDTH = 1000
CARD_DPI = 192
CARD_FOOTER_TEXT = "Create by GsCore & Power by sssysy/CalabiyauUID & Data by 白泉幽奈"

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass(frozen=True)
class CardTemplateContext:
    """HTML 卡片模板上下文基类。"""

    footer_text: str = CARD_FOOTER_TEXT


def render_template(template_name: str, context: CardTemplateContext) -> str:
    """加载指定单 HTML 模板并渲染为完整文档字符串。"""
    template = _ENV.get_template(template_name)
    return template.render(data=context)


async def render_html(
    html_content: str,
    *,
    width: int = CARD_WIDTH,
    default_font_size: float = 14.0,
) -> bytes:
    """按统一 2x DPI 与逻辑宽度参数将 HTML 渲染为 PNG 字节。"""
    return await render_html_to_bytes(
        html_content,
        max_width=width * 2,
        dpi=CARD_DPI,
        root_max_width=width,
        default_font_size=default_font_size,
        allow_refit=True,
        image_format="png",
        lang="zh",
    )


async def render_card(
    template_name: str,
    context: CardTemplateContext,
    *,
    width: int = CARD_WIDTH,
    default_font_size: float = 14.0,
) -> bytes:
    """渲染单 HTML 模板并输出 PNG 图片字节。"""
    html_content = render_template(template_name, context)
    return await render_html(
        html_content,
        width=width,
        default_font_size=default_font_size,
    )
