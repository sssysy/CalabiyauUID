"""封神榜 HTML 卡片。"""

from typing import Literal
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from collections.abc import Mapping

from ..render import CARD_WIDTH, CardTemplateContext, render_card, render_template
from .summary_card import tier_display
from ....api.dakanu import DakanuBannedEntry

_BEIJING_TZ = timezone(timedelta(hours=8))
_GRID_COLUMNS = 3
BannedSearchMode = Literal["list", "exact", "fuzzy"]


@dataclass(frozen=True)
class BannedItemView:
    index_text: str
    avatar: str
    initial: str
    nickname: str
    level_text: str
    uid_text: str
    tier_icon: str
    notice_date: str
    is_masked: bool


@dataclass(frozen=True)
class BannedTemplateContext(CardTemplateContext):
    title: str = "封神榜"
    result_summary: str = ""
    pagination_text: str = ""
    is_single: bool = False
    rows: tuple[tuple[BannedItemView | None, ...], ...] = ()


def _format_notice_date(published_at: int | None) -> str:
    if published_at is None or published_at <= 0:
        return ""
    return datetime.fromtimestamp(published_at, tz=_BEIJING_TZ).strftime("%Y-%m-%d")


def _format_tier_icon(segment: int | None, tier_images: Mapping[int, str]) -> str:
    if segment is None or segment <= 0:
        return ""
    _, _, tier_idx = tier_display(segment)
    return tier_images[tier_idx] if tier_idx > 0 and tier_idx in tier_images else ""


def _build_item_view(
    index: int,
    entry: DakanuBannedEntry,
    avatar_images: Mapping[int, str],
    tier_images: Mapping[int, str],
) -> BannedItemView:
    avatar_id = entry["avatarId"]
    avatar = avatar_images[avatar_id] if avatar_id is not None and avatar_id in avatar_images else ""
    nickname = entry["nickname"]
    initial = nickname[0] if nickname else "?"
    level = entry["level"]
    level_text = f"Lv.{level}" if level is not None and level > 0 else ""

    player_id = entry["playerId"]
    is_masked = player_id is None or not player_id
    if player_id is not None and player_id:
        uid_text = f"UID {player_id}"
    elif entry["maskedId"]:
        uid_text = f"UID {entry['maskedId']}"
    else:
        uid_text = "UID 未匹配"

    tier_icon = _format_tier_icon(entry["segment"], tier_images)
    return BannedItemView(
        index_text=f"#{index}",
        avatar=avatar,
        initial=initial,
        nickname=nickname,
        level_text=level_text,
        uid_text=uid_text,
        tier_icon=tier_icon,
        notice_date=_format_notice_date(entry["publishedAt"]),
        is_masked=is_masked,
    )


def _chunk_rows(items: list[BannedItemView], columns: int) -> tuple[tuple[BannedItemView | None, ...], ...]:
    if not items:
        return ()
    rows: list[tuple[BannedItemView | None, ...]] = []
    for start in range(0, len(items), columns):
        chunk: list[BannedItemView | None] = list(items[start : start + columns])
        while len(chunk) < columns:
            chunk.append(None)
        rows.append(tuple(chunk))
    return tuple(rows)


def _build_banned_context(
    entries: list[DakanuBannedEntry],
    total: int,
    avatar_images: Mapping[int, str],
    tier_images: Mapping[int, str],
    *,
    search_mode: BannedSearchMode = "list",
    page: int = 1,
    page_size: int = 21,
) -> BannedTemplateContext:
    items = [_build_item_view(idx, entry, avatar_images, tier_images) for idx, entry in enumerate(entries, start=1)]
    count = len(items)
    columns = 1 if count <= 1 else (2 if count == 2 else _GRID_COLUMNS)
    if search_mode == "exact":
        return BannedTemplateContext(
            title="封神榜查询",
            result_summary=f"共 {total} 个结果",
            is_single=count == 1,
            rows=_chunk_rows(items, columns),
        )
    if search_mode == "fuzzy":
        safe_page_size = max(1, page_size)
        total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
        return BannedTemplateContext(
            title="封神榜查询",
            pagination_text=f"第 {page} 页 共 {total_pages} 页 {total} 个结果",
            is_single=count == 1,
            rows=_chunk_rows(items, columns),
        )
    return BannedTemplateContext(
        title="封神榜",
        is_single=False,
        rows=_chunk_rows(items, columns),
    )


def render_banned_html(
    entries: list[DakanuBannedEntry],
    total: int,
    avatar_images: Mapping[int, str],
    tier_images: Mapping[int, str],
    *,
    search_mode: BannedSearchMode = "list",
    page: int = 1,
    page_size: int = 21,
) -> str:
    """生成封神榜完整 HTML 文档。"""
    context = _build_banned_context(
        entries, total, avatar_images, tier_images, search_mode=search_mode, page=page, page_size=page_size
    )
    return render_template("banned_card.html", context)


async def render_banned_card(
    entries: list[DakanuBannedEntry],
    total: int,
    avatar_images: Mapping[int, str],
    tier_images: Mapping[int, str],
    *,
    search_mode: BannedSearchMode = "list",
    page: int = 1,
    page_size: int = 21,
) -> bytes:
    """把封神榜记录渲染为 PNG 卡片。"""
    context = _build_banned_context(
        entries, total, avatar_images, tier_images, search_mode=search_mode, page=page, page_size=page_size
    )
    return await render_card(
        "banned_card.html",
        context,
        width=CARD_WIDTH,
        default_font_size=14,
    )
