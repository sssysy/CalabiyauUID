"""卡拉彼丘进行中活动时间轴 HTML 卡片渲染。"""

from datetime import datetime, timedelta
from dataclasses import dataclass

from .render import CardTemplateContext, render_card, render_template
from ...api.biligame_wiki import WikiActivityItem

_TICK_COUNT = 6
_URGENT_DAYS = 3
_WIDE_THRESHOLD_PCT = 55.0
_NARROW_THRESHOLD_PCT = 26.0
_WIKI_FOOTER_TEXT = "Create by GsCore & Power by sssysy/CalabiyauUID & Data by Biligame Wiki"


@dataclass(frozen=True)
class TimelineTickItem:
    """时间轴顶部刻度与竖向辅助线。"""

    left_pct: str
    label: str
    align_cls: str


@dataclass(frozen=True)
class TimelineBarItem:
    """单个活动条的布局与文本数据。"""

    title: str
    date_text: str
    rem_text: str
    image_uri: str
    left_pct: str
    width_pct: str
    is_urgent: bool
    is_wide: bool


@dataclass(frozen=True)
class ActivityTimelineContext(CardTemplateContext):
    """活动时间轴卡片渲染上下文。"""

    banner_bg_uri: str = ""
    now_text: str = ""
    today_label: str = ""
    now_pct: str = "0.000"
    show_now_line: bool = False
    ticks: tuple[TimelineTickItem, ...] = ()
    bars: tuple[TimelineBarItem, ...] = ()


def _format_remaining(remaining: timedelta, *, is_narrow: bool) -> str:
    total_seconds = max(0, int(remaining.total_seconds()))
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    if days >= 1:
        return f"剩{days}天" if is_narrow else f"剩余{days}天"
    if hours >= 1:
        return f"剩{hours}h" if is_narrow else f"剩余{hours}小时"
    minutes = max(1, (total_seconds % 3600) // 60)
    return f"剩{minutes}m" if is_narrow else f"剩余{minutes}分钟"


def build_activity_timeline_context(
    activities: list[WikiActivityItem],
    image_uris: dict[str, str],
    banner_bg_uri: str,
    now: datetime,
) -> ActivityTimelineContext:
    """根据进行中活动列表与本地图片 URI 组装时间轴模板上下文。"""
    permanent = sorted(
        (item for item in activities if item.is_permanent),
        key=lambda item: item.start_at,
    )
    timed = sorted(
        (item for item in activities if not item.is_permanent),
        key=lambda item: (item.start_at, item.end_at),
    )

    now_text = now.strftime("%Y-%m-%d %H:%M")
    today_label = f"今日 {now.month}.{now.day}"

    if not permanent and not timed:
        return ActivityTimelineContext(
            footer_text=_WIKI_FOOTER_TEXT,
            banner_bg_uri=banner_bg_uri,
            now_text=now_text,
            today_label=today_label,
        )

    if timed:
        min_start = min(item.start_at for item in timed)
        max_end = max(item.end_at for item in timed)
    else:
        min_start = now - timedelta(days=15)
        max_end = now + timedelta(days=15)

    total_seconds = max(1.0, (max_end - min_start).total_seconds())

    bars: list[TimelineBarItem] = []
    for item in permanent:
        uri = image_uris[item.image_name] if item.image_name in image_uris else ""
        bars.append(
            TimelineBarItem(
                title=item.title,
                date_text=f"{item.start_at.year}.{item.start_at.month}.{item.start_at.day} 起",
                rem_text="常驻",
                image_uri=uri,
                left_pct="0.000",
                width_pct="100.000",
                is_urgent=False,
                is_wide=True,
            )
        )

    for item in timed:
        left_val = (item.start_at - min_start).total_seconds() / total_seconds * 100.0
        width_val = max(
            0.5,
            (item.end_at - item.start_at).total_seconds() / total_seconds * 100.0,
        )
        remaining = item.end_at - now
        is_narrow = width_val < _NARROW_THRESHOLD_PCT
        is_wide = width_val >= _WIDE_THRESHOLD_PCT
        uri = image_uris[item.image_name] if item.image_name in image_uris else ""
        bars.append(
            TimelineBarItem(
                title=item.title,
                date_text=(
                    f"{item.start_at.month}.{item.start_at.day}"
                    f"~{item.end_at.month}.{item.end_at.day}"
                ),
                rem_text=_format_remaining(remaining, is_narrow=is_narrow),
                image_uri=uri,
                left_pct=f"{left_val:.3f}",
                width_pct=f"{width_val:.3f}",
                is_urgent=remaining.total_seconds() < _URGENT_DAYS * 86400,
                is_wide=is_wide,
            )
        )

    ticks: list[TimelineTickItem] = []
    for step in range(_TICK_COUNT + 1):
        frac = step / _TICK_COUNT
        tick_dt = min_start + timedelta(seconds=total_seconds * frac)
        align_cls = "is-start" if step == 0 else ("is-end" if step == _TICK_COUNT else "")
        ticks.append(
            TimelineTickItem(
                left_pct=f"{frac * 100.0:.3f}",
                label=f"{tick_dt.month}.{tick_dt.day}",
                align_cls=align_cls,
            )
        )

    now_val = max(0.0, min(100.0, (now - min_start).total_seconds() / total_seconds * 100.0))
    return ActivityTimelineContext(
        footer_text=_WIKI_FOOTER_TEXT,
        banner_bg_uri=banner_bg_uri,
        now_text=now_text,
        today_label=today_label,
        now_pct=f"{now_val:.3f}",
        show_now_line=True,
        ticks=tuple(ticks),
        bars=tuple(bars),
    )


def render_activity_timeline_html(
    activities: list[WikiActivityItem],
    image_uris: dict[str, str],
    banner_bg_uri: str,
    now: datetime,
) -> str:
    """渲染活动时间轴 HTML 字符串。"""
    context = build_activity_timeline_context(activities, image_uris, banner_bg_uri, now)
    return render_template("activity_timeline_card.html", context)


async def render_activity_timeline_card(
    activities: list[WikiActivityItem],
    image_uris: dict[str, str],
    banner_bg_uri: str,
    now: datetime,
) -> bytes:
    """将进行中活动时间轴渲染为 PNG 图片字节。"""
    context = build_activity_timeline_context(activities, image_uris, banner_bg_uri, now)
    return await render_card("activity_timeline_card.html", context)
