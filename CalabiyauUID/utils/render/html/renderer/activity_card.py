"""玩家活跃趋势 HTML 卡片。"""

from datetime import datetime
from dataclasses import dataclass

from ..render import CardTemplateContext, render_card, render_template
from ....api.dakanu.models.community import DakanuGameActivity

_CHART_WIDTH = 920.0
_CHART_HEIGHT = 336.0
_PAD_LEFT = 66.0
_PAD_RIGHT = 24.0
_PAD_TOP = 44.0
_PAD_BOTTOM = 74.0
_PLOT_WIDTH = _CHART_WIDTH - _PAD_LEFT - _PAD_RIGHT
_PLOT_HEIGHT = _CHART_HEIGHT - _PAD_TOP - _PAD_BOTTOM
_AXIS_Y = _PAD_TOP + _PLOT_HEIGHT

_RANGE_LABELS: dict[str, str] = {
    "6h": "6小时",
    "24h": "24小时",
    "7d": "7天",
    "30d": "30天",
}


@dataclass(frozen=True)
class GridLineItem:
    y: str
    label_y: str
    label: str


@dataclass(frozen=True)
class XTickItem:
    x: str
    y1: str
    y2: str
    left_pct: str
    top_pct: str
    label: str


@dataclass(frozen=True)
class ChartDotItem:
    cx: str
    cy: str


@dataclass(frozen=True)
class ExtremaOverlay:
    line_y: str
    cx: str
    cy: str
    badge_left_pct: str
    badge_top_pct: str
    badge_tx: str
    badge_text: str


@dataclass(frozen=True)
class ActivityTemplateContext(CardTemplateContext):
    range_label: str = "24小时"
    region_label: str = "CN"
    daily_text: str = "—"
    active30_text: str = "—"
    has_points: bool = False
    chart_width: str = "920"
    chart_height: str = "336"
    pad_left: str = "66.0"
    pad_top: str = "44.0"
    plot_right: str = "896.0"
    axis_y: str = "280.0"
    grid_lines: tuple[GridLineItem, ...] = ()
    x_ticks: tuple[XTickItem, ...] = ()
    area_points: str = ""
    line_points: str = ""
    dots: tuple[ChartDotItem, ...] = ()
    max_extrema: ExtremaOverlay | None = None
    min_extrema: ExtremaOverlay | None = None


def _format_ts(ts: int, fmt: str) -> str:
    return datetime.fromtimestamp(ts).strftime(fmt)


def _badge_position(x: float, y: float, *, prefer_above: bool) -> tuple[str, str, str]:
    left_pct = f"{x / _CHART_WIDTH * 100.0:.2f}"
    if x < _PAD_LEFT + 150.0:
        tx = "0%"
    elif x > _CHART_WIDTH - _PAD_RIGHT - 150.0:
        tx = "-100%"
    else:
        tx = "-50%"
    if prefer_above:
        top_px = max(14.0, y - 30.0)
    else:
        top_px = y + 8.0 if _AXIS_Y - y >= 32.0 else y - 30.0
    top_pct = f"{top_px / _CHART_HEIGHT * 100.0:.2f}"
    return left_pct, top_pct, tx


def build_activity_context(activity: DakanuGameActivity) -> ActivityTemplateContext:
    """把 Dakanu 活跃趋势接口响应整理为模板上下文。"""
    est_points = activity.estimate.points
    last_est = est_points[-1] if est_points else None
    daily_text = f"{last_est.daily:,}" if last_est is not None else "—"
    active30_text = f"{last_est.active30d:,}" if last_est is not None else "—"

    range_val = activity.range
    range_label = _RANGE_LABELS[range_val] if range_val in _RANGE_LABELS else range_val
    region_label = activity.region.upper() if activity.region else "CN"

    pts = activity.points
    if not pts:
        return ActivityTemplateContext(
            range_label=range_label,
            region_label=region_label,
            daily_text=daily_text,
            active30_text=active30_text,
            has_points=False,
        )

    indices = [float(pt.index) for pt in pts]
    raw_min = min(indices)
    raw_max = max(indices)
    span = raw_max - raw_min
    margin = max(8.0, span * 0.16)
    y_min = 0.0 if raw_min <= 10.0 else max(0.0, round((raw_min - margin) / 5.0) * 5.0)
    y_max = 100.0 if raw_max >= 90.0 else min(100.0, round((raw_max + margin) / 5.0) * 5.0)
    if y_max <= y_min:
        y_max = min(100.0, y_min + 10.0)
    y_span = y_max - y_min

    t_start = pts[0].at
    t_end = pts[-1].at
    t_span = max(1, t_end - t_start)

    coords: list[tuple[int, float, float, float]] = []
    for pt in pts:
        x = _PAD_LEFT + ((pt.at - t_start) / t_span) * _PLOT_WIDTH
        val = float(pt.index)
        y = _PAD_TOP + _PLOT_HEIGHT * (1.0 - (val - y_min) / y_span)
        coords.append((pt.at, val, x, y))

    grid_lines: list[GridLineItem] = []
    for idx in range(5):
        frac = idx / 4.0
        val = y_min + y_span * frac
        yy = _PAD_TOP + _PLOT_HEIGHT * (1.0 - frac)
        grid_lines.append(
            GridLineItem(
                y=f"{yy:.1f}",
                label_y=f"{yy + 4.0:.1f}",
                label=f"{val:.0f}",
            )
        )

    count = len(coords)
    if count <= 32:
        tick_indices = list(range(count))
    else:
        tick_count = 24
        tick_indices = sorted({round(i * (count - 1) / max(1, tick_count - 1)) for i in range(tick_count)})
    x_fmt = "%H:%M" if range_val == "6h" else "%m-%d %H:%M" if range_val == "24h" else "%m-%d"
    x_ticks: list[XTickItem] = []
    for ci in tick_indices:
        at, _, xx, _ = coords[ci]
        cx = xx + 2.0 - 25.5
        cy = _AXIS_Y + 9.0 + 25.5
        x_ticks.append(
            XTickItem(
                x=f"{xx:.1f}",
                y1=f"{_AXIS_Y:.1f}",
                y2=f"{_AXIS_Y + 5.0:.1f}",
                left_pct=f"{cx / _CHART_WIDTH * 100.0:.2f}",
                top_pct=f"{cy / _CHART_HEIGHT * 100.0:.2f}",
                label=_format_ts(at, x_fmt),
            )
        )

    line_points = " ".join(f"{x:.1f},{y:.1f}" for _, _, x, y in coords)
    area_points = f"{coords[0][2]:.1f},{_AXIS_Y:.1f} " + line_points + f" {coords[-1][2]:.1f},{_AXIS_Y:.1f}"

    dots: tuple[ChartDotItem, ...] = (
        tuple(ChartDotItem(cx=f"{x:.1f}", cy=f"{y:.1f}") for _, _, x, y in coords) if count <= 32 else ()
    )

    max_at, max_val, max_x, max_y = max(coords, key=lambda item: item[1])
    min_at, min_val, min_x, min_y = min(coords, key=lambda item: item[1])
    max_left, max_top, max_tx = _badge_position(max_x, max_y, prefer_above=True)
    min_left, min_top, min_tx = _badge_position(min_x, min_y, prefer_above=False)

    return ActivityTemplateContext(
        range_label=range_label,
        region_label=region_label,
        daily_text=daily_text,
        active30_text=active30_text,
        has_points=True,
        chart_width=f"{_CHART_WIDTH:.0f}",
        chart_height=f"{_CHART_HEIGHT:.0f}",
        pad_left=f"{_PAD_LEFT:.1f}",
        pad_top=f"{_PAD_TOP:.1f}",
        plot_right=f"{_CHART_WIDTH - _PAD_RIGHT:.1f}",
        axis_y=f"{_AXIS_Y:.1f}",
        grid_lines=tuple(grid_lines),
        x_ticks=tuple(x_ticks),
        area_points=area_points,
        line_points=line_points,
        dots=dots,
        max_extrema=ExtremaOverlay(
            line_y=f"{max_y:.1f}",
            cx=f"{max_x:.1f}",
            cy=f"{max_y:.1f}",
            badge_left_pct=max_left,
            badge_top_pct=max_top,
            badge_tx=max_tx,
            badge_text=f"↑ 最高 {max_val:.1f} · {_format_ts(max_at, '%m-%d %H:%M')}",
        ),
        min_extrema=ExtremaOverlay(
            line_y=f"{min_y:.1f}",
            cx=f"{min_x:.1f}",
            cy=f"{min_y:.1f}",
            badge_left_pct=min_left,
            badge_top_pct=min_top,
            badge_tx=min_tx,
            badge_text=f"↓ 最低 {min_val:.1f} · {_format_ts(min_at, '%m-%d %H:%M')}",
        ),
    )


def render_activity_html(activity: DakanuGameActivity) -> str:
    """渲染玩家活跃趋势 HTML 字符串。"""
    context = build_activity_context(activity)
    return render_template("activity_card.html", context)


async def render_activity_card(activity: DakanuGameActivity) -> bytes:
    """把玩家活跃趋势渲染为 PNG 图片字节。"""
    context = build_activity_context(activity)
    return await render_card("activity_card.html", context)
