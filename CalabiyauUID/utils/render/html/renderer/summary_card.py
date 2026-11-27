"""战绩总览静态卡片。"""

import math
from datetime import datetime
from dataclasses import field, dataclass
from collections.abc import Mapping

from ..render import CARD_WIDTH, CardTemplateContext, render_card, render_template
from .matches_card import MatchCardItem, MatchCardAssets, build_match_card_item
from ....helper.maps import ROLE_POSITIONS, resolve_role_meta, get_role_display_names
from ....helper.recent_matches import MatchView
from ....api.dakanu.models.match import DakanuMatch
from ....api.dakanu.models.player import (
    DakanuMode,
    DakanuRole,
    DakanuMedal,
    DakanuRival,
    DakanuPlayer,
    DakanuTeamUp,
    DakanuLeisure,
    DakanuProfile,
    DakanuSummary,
    DakanuPresence,
)

_TREND_POINTS = 20
_RECENT_FORM_LIMIT = 20
_ACTIVITY_HOURS_LIMIT = 100
_SEASON_RECENT_MATCHES_LIMIT = 5

_TREND_WIDTH = 576.0
_TREND_HEIGHT = 224.0
_TREND_PAD_LEFT = 48.0
_TREND_PAD_RIGHT = 18.0
_TREND_PAD_TOP = 32.0
_TREND_PAD_BOTTOM = 46.0
_TREND_PLOT_WIDTH = _TREND_WIDTH - _TREND_PAD_LEFT - _TREND_PAD_RIGHT
_TREND_PLOT_HEIGHT = _TREND_HEIGHT - _TREND_PAD_TOP - _TREND_PAD_BOTTOM
_TREND_AXIS_Y = _TREND_PAD_TOP + _TREND_PLOT_HEIGHT

_PRIVACY_LABELS: dict[str, str] = {
    "open": "生涯公开",
    "hidden": "生涯隐藏",
    "unavailable": "不可查询",
}
_PRESENCE_LABELS: dict[str, str] = {
    "online": "在线",
    "away": "离开",
    "busy": "忙碌",
    "invisible": "隐身",
    "offline": "离线",
}

_TIERS = (
    ("至纯物质", 1, 3, ("III", "II", "I"), "#6c7178", 1),
    ("升格分子", 4, 6, ("III", "II", "I"), "#c07a52", 2),
    ("虚空原子", 7, 10, ("IV", "III", "II", "I"), "#9aa7b5", 3),
    ("聚变质子", 11, 14, ("IV", "III", "II", "I"), "#d0a63c", 4),
    ("自由中子", 15, 18, ("IV", "III", "II", "I"), "#28b3a4", 5),
    ("束缚电子", 19, 23, ("V", "IV", "III", "II", "I"), "#3f8fd6", 6),
    ("禁闭夸克", 24, 28, ("V", "IV", "III", "II", "I"), "#9b5cd6", 7),
    ("无限超弦", 29, 29, (), "#d94a44", 8),
    ("奇点", 30, 30, (), "#d84a4a", 9),
)

_CHALLENGE_TABLE: tuple[tuple[int, str, str, int, int, tuple[tuple[str, int, int, int], ...]], ...] = (
    (
        1,
        "青铜",
        "#b97859",
        0,
        1099,
        (("V", 0, 199, 40), ("IV", 200, 399, 40), ("III", 400, 599, 40), ("II", 600, 799, 40), ("I", 800, 1099, 60)),
    ),
    (
        2,
        "白银",
        "#b8bcc4",
        1100,
        2749,
        (
            ("V", 1100, 1399, 60),
            ("IV", 1400, 1699, 60),
            ("III", 1700, 1999, 60),
            ("II", 2000, 2299, 60),
            ("I", 2300, 2749, 90),
        ),
    ),
    (
        3,
        "黄金",
        "#d5ab50",
        2750,
        5199,
        (
            ("V", 2750, 3199, 90),
            ("IV", 3200, 3649, 90),
            ("III", 3650, 4099, 90),
            ("II", 4100, 4549, 90),
            ("I", 4550, 5199, 130),
        ),
    ),
    (
        4,
        "铂金",
        "#e2ddd7",
        5200,
        8699,
        (
            ("V", 5200, 5849, 130),
            ("IV", 5850, 6499, 130),
            ("III", 6500, 7149, 130),
            ("II", 7150, 7799, 130),
            ("I", 7800, 8699, 180),
        ),
    ),
    (
        5,
        "翡翠",
        "#59a968",
        8700,
        13449,
        (
            ("V", 8700, 9599, 180),
            ("IV", 9600, 10499, 180),
            ("III", 10500, 11399, 180),
            ("II", 11400, 12299, 180),
            ("I", 12300, 13449, 230),
        ),
    ),
    (
        6,
        "钻石",
        "#68b5dc",
        13450,
        19499,
        (
            ("V", 13450, 14599, 230),
            ("IV", 14600, 15749, 230),
            ("III", 15750, 16899, 230),
            ("II", 16900, 18049, 230),
            ("I", 18050, 19499, 290),
        ),
    ),
    (
        7,
        "大师",
        "#a35ed3",
        19500,
        27099,
        (
            ("V", 19500, 20949, 290),
            ("IV", 20950, 22399, 290),
            ("III", 22400, 23849, 290),
            ("II", 23850, 25299, 290),
            ("I", 25300, 27099, 360),
        ),
    ),
    (
        8,
        "传奇",
        "#d65358",
        27100,
        36099,
        (
            ("V", 27100, 28899, 360),
            ("IV", 28900, 30699, 360),
            ("III", 30700, 32499, 360),
            ("II", 32500, 34299, 360),
            ("I", 34300, 36099, 360),
        ),
    ),
    (9, "王者", "#d7b15c", 36100, 10**9, ()),
)


@dataclass(frozen=True)
class SummaryAssets:
    avatar: str
    tier_icon: str
    top_tier_icon: str
    challenge_icon: str
    baseplate: str
    frame: str
    role_images: Mapping[int, str]
    clan_name: str
    leisure: DakanuLeisure | None
    avatar_frame: str = ""
    medal_images: Mapping[int, str] = field(default_factory=dict)
    avatar_images: Mapping[int, str] = field(default_factory=dict)
    map_images: Mapping[str, str] = field(default_factory=dict)
    recent_match_views: tuple[MatchView, ...] = ()
    is_season_view: bool = False


@dataclass(frozen=True)
class EmptySummaryTemplateContext(CardTemplateContext):
    message: str = ""


@dataclass(frozen=True)
class ChallengeBlock:
    icon: str
    name: str
    color: str
    score: int
    win_rate: str
    star: int
    has_detail: bool
    progress_label: str
    progress_text: str
    progress_pct: str


@dataclass(frozen=True)
class MedalItem:
    image: str
    left_pct: str
    top_pct: str
    width_pct: str
    transform: str


@dataclass(frozen=True)
class RankedStripBlock:
    rounds: int
    wins: int
    win_rate: str
    kda: str
    kd: str
    round_avg_damage: str


@dataclass(frozen=True)
class RecentRoleItem:
    image: str
    name: str
    record_text: str
    win_rate: str
    kda: str


@dataclass(frozen=True)
class PositionDistItem:
    name: str
    count: int
    bar_pct: str


@dataclass(frozen=True)
class RecentFormBlock:
    has_data: bool
    games: int
    wins: int
    losses: int
    draws: int
    win_rate_pct: int
    win_rate_text: str
    avg_kda_line: str
    kda_ratio: str
    kill_participation: str
    top_roles: tuple[RecentRoleItem, ...]
    positions: tuple[PositionDistItem, ...]


@dataclass(frozen=True)
class HourCellItem:
    hour_label: str
    level: int


@dataclass(frozen=True)
class ActivityHoursBlock:
    has_data: bool
    sample_count: int
    peak_text: str
    morning_cells: tuple[HourCellItem, ...]
    afternoon_cells: tuple[HourCellItem, ...]


@dataclass(frozen=True)
class RelationshipItem:
    avatar: str
    initial: str
    nickname: str
    meta_text: str
    win_rate: str


@dataclass(frozen=True)
class TrendDot:
    x: str
    y: str


@dataclass(frozen=True)
class TrendGridLine:
    y: str
    label_y: str
    label: str


@dataclass(frozen=True)
class TrendXTick:
    x: str
    y1: str
    y2: str
    left_pct: str
    top_pct: str
    label: str


@dataclass(frozen=True)
class TrendExtrema:
    line_y: str
    cx: str
    cy: str
    badge_left_pct: str
    badge_top_pct: str
    badge_tx: str
    badge_text: str


@dataclass(frozen=True)
class TrendBlock:
    has_chart: bool
    chart_width: str
    chart_height: str
    pad_left: str
    pad_top: str
    plot_right: str
    axis_y: str
    grid_lines: tuple[TrendGridLine, ...]
    x_ticks: tuple[TrendXTick, ...]
    area_points: str
    line_points: str
    dots: tuple[TrendDot, ...]
    max_extrema: TrendExtrema | None
    min_extrema: TrendExtrema | None
    match_count: int
    tier_label: str
    tier_color: str
    score_text: str
    range_tier_label: str
    range_score_text: str
    net_class: str
    net_text: str
    wins: int
    losses: int
    draws: int


@dataclass(frozen=True)
class RoleItem:
    image: str
    name: str
    faction_name: str
    faction_color: str
    position_name: str
    win_rate: str
    count: int
    kd: str
    avg_damage: str
    max_kill: int
    bar_pct: str


@dataclass(frozen=True)
class ModeItem:
    label: str
    rounds: int
    win_rate: str
    kd: str
    avg_damage: str
    round_avg_damage: str
    avg_kill: str
    headshot_rate: str
    mvp_rate: str


@dataclass(frozen=True)
class SummaryTemplateContext(CardTemplateContext):
    nickname: str = ""
    uid: str = ""
    season: str = ""
    is_season_view: bool = False
    avatar: str = ""
    avatar_frame: str = ""
    region_label: str = ""
    presence_text: str = ""
    presence_online: bool = False
    privacy_label: str = ""
    verify_label: str = ""
    clan_name: str = ""
    level: int = 0
    laud: int = 0
    previous_names: str = "无"
    like_count: int = 0
    tier_icon: str = ""
    tier_label: str = ""
    tier_color: str = ""
    score_sub_text: str = ""
    rank_pos: str = ""
    season_top_label: str = ""
    historical_season: int = 0
    top_tier_icon: str = ""
    top_label: str = ""
    top_color: str = ""
    top_score_sub_text: str = ""
    historical_pos: str = "—"
    challenge: ChallengeBlock | None = None
    baseplate: str = ""
    frame: str = ""
    medals: tuple[MedalItem, ...] = ()
    rounds: int = 0
    wins: int = 0
    losses: int = 0
    win_rate_text: str = ""
    bar_width_pct: str = "0.0"
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    kd_text: str = ""
    kda_text: str = ""
    total_damage: str = ""
    avg_damage: str = ""
    round_avg_damage: str = ""
    avg_kill: str = ""
    avg_death: str = ""
    avg_assist: str = ""
    headshot_rate: str = ""
    mvp_rate: str = ""
    mvp_count: int = 0
    ranked_strip: RankedStripBlock | None = None
    recent_form: RecentFormBlock | None = None
    trend: TrendBlock | None = None
    activity_hours: ActivityHoursBlock | None = None
    roles: tuple[RoleItem, ...] = ()
    modes: tuple[ModeItem, ...] = ()
    recent_matches: tuple[MatchCardItem, ...] = ()
    team_ups: tuple[RelationshipItem, ...] = ()
    rivals: tuple[RelationshipItem, ...] = ()


def _tier(segment: int) -> tuple[str, str, str]:
    for name, start, end, divisions, color, tier_index in _TIERS:
        if start <= segment <= end:
            division = divisions[segment - start] if divisions else ""
            label = f"{name} {division}" if division else name
            return label, color, str(tier_index)
    return "未定级", "#8d99ad", ""


def tier_display(segment: int) -> tuple[str, str, int]:
    """返回段位展示名、主题色与图标编号；未定级时图标编号为 0。"""
    label, color, index_text = _tier(segment)
    return label, color, int(index_text) if index_text else 0


def tier_index(segment: int) -> int:
    """按段位返回素材目录里的段位图标编号；未定级返回 0。"""
    _, _, tier_index = _tier(segment)
    return int(tier_index) if tier_index else 0


def challenge_tier_index(segment: int) -> int:
    """挑战赛段位图标编号；段位范围 1..41。"""
    if segment < 1 or segment > 41:
        return 0
    return min(9, ((segment - 1) // 5) + 1)


def _challenge_label(segment: int) -> tuple[str, str]:
    label, color, _ = challenge_tier_display(segment)
    return label, color


def challenge_tier_display(segment: int) -> tuple[str, str, int]:
    """返回挑战赛段位名、主题色与图标编号；范围外返回空串与 0。"""
    tiers = (
        ("青铜", "#b97859", ("V", "IV", "III", "II", "I")),
        ("白银", "#b8bcc4", ("V", "IV", "III", "II", "I")),
        ("黄金", "#d5ab50", ("V", "IV", "III", "II", "I")),
        ("铂金", "#e2ddd7", ("V", "IV", "III", "II", "I")),
        ("翡翠", "#59a968", ("V", "IV", "III", "II", "I")),
        ("钻石", "#68b5dc", ("V", "IV", "III", "II", "I")),
        ("大师", "#a35ed3", ("V", "IV", "III", "II", "I")),
        ("传奇", "#d65358", ("V", "IV", "III", "II", "I")),
        ("王者", "#d7b15c", ()),
    )
    if segment < 1 or segment > 41:
        return "", "", 0
    tier_idx = min(9, ((segment - 1) // 5) + 1)
    name, color, divisions = tiers[tier_idx - 1]
    if not divisions:
        return name, color, tier_idx
    div_idx = (segment - 1) % 5
    return f"{name} {divisions[div_idx]}", color, tier_idx


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _num(value: float, digits: int = 0) -> str:
    if digits == 0:
        return f"{value:,.0f}"
    return f"{value:,.{digits}f}"


def _score_to_segment(score: int) -> int:
    if score <= 0:
        return 0
    if score >= 2800:
        return 29
    return min(28, max(1, math.ceil(score / 100.0)))


def _challenge_segment_from_score(score: int) -> int:
    if score < 0:
        return 0
    seg = 1
    for _, _, _, t_from, t_to, divisions in _CHALLENGE_TABLE:
        if not divisions:
            if score >= t_from:
                return seg
            continue
        if t_from <= score <= t_to:
            for idx, (_, d_from, d_to, _) in enumerate(divisions):
                if d_from <= score <= d_to:
                    return seg + idx
        seg += len(divisions)
    return 41 if score >= 36100 else 0


def resolve_challenge_tier(leisure: DakanuLeisure | None, presence: DakanuPresence | None) -> int:
    """按挑战赛档案或在线状态兜底计算挑战赛图标编号；无数据时返回 0。"""
    if leisure is not None and leisure.segment is not None:
        seg = leisure.segment
        if 1 <= seg <= 41:
            return challenge_tier_index(seg)
    if presence is not None:
        if presence.leisureSegment is not None:
            idx = challenge_tier_index(presence.leisureSegment)
            if idx > 0:
                return idx
        if presence.leisureScore is not None:
            seg = _challenge_segment_from_score(presence.leisureScore)
            return challenge_tier_index(seg)
    return 0


def extract_medal_ids(player: DakanuPlayer) -> list[int]:
    """提取玩家基板佩戴的勋章 ID（按出现顺序去重）。"""
    medal_ids: list[int] = []
    seen: set[int] = set()
    for item in player.medals:
        if isinstance(item, int):
            medal_id = item
        elif isinstance(item, DakanuMedal) and item.id is not None:
            medal_id = item.id
        else:
            continue
        if medal_id > 0 and medal_id not in seen:
            seen.add(medal_id)
            medal_ids.append(medal_id)
    return medal_ids


def _trend_matches(profile: DakanuProfile) -> list[DakanuMatch]:
    matches = [match for match in profile.matches if "RANK" in match.mode and match.divisionScore is not None][
        :_TREND_POINTS
    ]
    if matches:
        return list(reversed(matches))
    history = [match for match in profile.historyMatches if "RANK" in match.mode and match.divisionScore is not None][
        :_TREND_POINTS
    ]
    return list(reversed(history))


def _trend_badge_position(x: float, y: float, *, prefer_above: bool) -> tuple[str, str, str]:
    left_pct = f"{x / _TREND_WIDTH * 100.0:.2f}"
    if x < _TREND_PAD_LEFT + 110.0:
        tx = "0%"
    elif x > _TREND_WIDTH - _TREND_PAD_RIGHT - 110.0:
        tx = "-100%"
    else:
        tx = "-50%"
    if prefer_above:
        top_px = max(8.0, y - 28.0)
    else:
        top_px = y + 8.0 if _TREND_AXIS_Y - y >= 30.0 else y - 28.0
    top_pct = f"{top_px / _TREND_HEIGHT * 100.0:.2f}"
    return left_pct, top_pct, tx


def _build_trend(profile: DakanuProfile) -> TrendBlock:
    matches = _trend_matches(profile)
    rank = profile.rank
    scores = [match.divisionScore for match in matches if match.divisionScore is not None]
    net = scores[-1] - scores[0] if len(scores) >= 2 else 0
    wins = sum(1 for match in matches if match.result == "win")
    losses = sum(1 for match in matches if match.result == "lose")
    draws = sum(1 for match in matches if match.result == "draw")
    tier_label, tier_color, _ = _tier(rank.segment)
    net_class = "is-up" if net >= 0 else "is-down"
    net_text = f"+{net}" if net >= 0 else str(net)
    grade_score = rank.gradeScore
    display_score = rank.divisionScore if rank.divisionScore > 0 else grade_score
    score_text = f"当前段位分 {display_score}" if rank.divisionScore > 0 else f"当前积分 {display_score}"

    has_chart = len(matches) >= 2 and len(scores) >= 2
    if not has_chart:
        return TrendBlock(
            has_chart=False,
            chart_width=f"{_TREND_WIDTH:.0f}",
            chart_height=f"{_TREND_HEIGHT:.0f}",
            pad_left=f"{_TREND_PAD_LEFT:.1f}",
            pad_top=f"{_TREND_PAD_TOP:.1f}",
            plot_right=f"{_TREND_WIDTH - _TREND_PAD_RIGHT:.1f}",
            axis_y=f"{_TREND_AXIS_Y:.1f}",
            grid_lines=(),
            x_ticks=(),
            area_points="",
            line_points="",
            dots=(),
            max_extrema=None,
            min_extrema=None,
            match_count=len(matches),
            tier_label=tier_label,
            tier_color=tier_color,
            score_text=score_text,
            range_tier_label="—",
            range_score_text="—",
            net_class=net_class,
            net_text=net_text,
            wins=wins,
            losses=losses,
            draws=draws,
        )

    raw_min = float(min(scores))
    raw_max = float(max(scores))
    span = raw_max - raw_min
    margin = max(10.0, span * 0.16)
    y_min = max(0.0, math.floor((raw_min - margin) / 10.0) * 10.0)
    y_max = math.ceil((raw_max + margin) / 10.0) * 10.0
    if y_max <= y_min:
        y_max = y_min + 20.0
    y_span = y_max - y_min

    coords: list[tuple[int, int, float, float]] = []
    count = len(matches)
    for index, match in enumerate(matches):
        score = match.divisionScore
        if score is None:
            continue
        x_pos = _TREND_PAD_LEFT + index * (_TREND_PLOT_WIDTH / max(1, count - 1))
        y_pos = _TREND_PAD_TOP + _TREND_PLOT_HEIGHT * (1.0 - (float(score) - y_min) / y_span)
        coords.append((match.playedAt, score, x_pos, y_pos))

    grid_lines: list[TrendGridLine] = []
    for idx in range(5):
        frac = idx / 4.0
        val = y_min + y_span * frac
        yy = _TREND_PAD_TOP + _TREND_PLOT_HEIGHT * (1.0 - frac)
        grid_lines.append(
            TrendGridLine(
                y=f"{yy:.1f}",
                label_y=f"{yy + 4.0:.1f}",
                label=f"{val:.0f}",
            )
        )

    day_set = {datetime.fromtimestamp(at).strftime("%Y-%m-%d") for at, _, _, _ in coords}
    tick_fmt = "%H:%M" if len(day_set) <= 1 else "%m-%d"
    if len(coords) <= 10:
        tick_indices = list(range(len(coords)))
    else:
        tick_indices = sorted({round(i * (len(coords) - 1) / 9) for i in range(10)})
    x_ticks: list[TrendXTick] = []
    for ci in tick_indices:
        at, _, xx, _ = coords[ci]
        cx = xx + 2.0 - 20.0
        cy = _TREND_AXIS_Y + 8.0 + 18.0
        x_ticks.append(
            TrendXTick(
                x=f"{xx:.1f}",
                y1=f"{_TREND_AXIS_Y:.1f}",
                y2=f"{_TREND_AXIS_Y + 4.0:.1f}",
                left_pct=f"{cx / _TREND_WIDTH * 100.0:.2f}",
                top_pct=f"{cy / _TREND_HEIGHT * 100.0:.2f}",
                label=datetime.fromtimestamp(at).strftime(tick_fmt),
            )
        )

    line_points = " ".join(f"{x:.1f},{y:.1f}" for _, _, x, y in coords)
    area_points = f"{coords[0][2]:.1f},{_TREND_AXIS_Y:.1f} " + line_points + f" {coords[-1][2]:.1f},{_TREND_AXIS_Y:.1f}"
    dots = tuple(TrendDot(x=f"{x:.1f}", y=f"{y:.1f}") for _, _, x, y in coords)

    max_at, max_val, max_x, max_y = max(coords, key=lambda item: item[1])
    min_at, min_val, min_x, min_y = min(coords, key=lambda item: item[1])
    max_left, max_top, max_tx = _trend_badge_position(max_x, max_y, prefer_above=True)
    min_left, min_top, min_tx = _trend_badge_position(min_x, min_y, prefer_above=False)

    low_tier, _, _ = _tier(_score_to_segment(int(raw_min)))
    high_tier, _, _ = _tier(_score_to_segment(int(raw_max)))
    range_tier_label = low_tier if low_tier == high_tier else f"{low_tier} – {high_tier}"
    range_score_text = f"{int(raw_min)} ~ {int(raw_max)} 分"

    return TrendBlock(
        has_chart=True,
        chart_width=f"{_TREND_WIDTH:.0f}",
        chart_height=f"{_TREND_HEIGHT:.0f}",
        pad_left=f"{_TREND_PAD_LEFT:.1f}",
        pad_top=f"{_TREND_PAD_TOP:.1f}",
        plot_right=f"{_TREND_WIDTH - _TREND_PAD_RIGHT:.1f}",
        axis_y=f"{_TREND_AXIS_Y:.1f}",
        grid_lines=tuple(grid_lines),
        x_ticks=tuple(x_ticks),
        area_points=area_points,
        line_points=line_points,
        dots=dots,
        max_extrema=TrendExtrema(
            line_y=f"{max_y:.1f}",
            cx=f"{max_x:.1f}",
            cy=f"{max_y:.1f}",
            badge_left_pct=max_left,
            badge_top_pct=max_top,
            badge_tx=max_tx,
            badge_text=f"↑ 最高 {max_val} · {datetime.fromtimestamp(max_at).strftime('%m-%d %H:%M')}",
        ),
        min_extrema=TrendExtrema(
            line_y=f"{min_y:.1f}",
            cx=f"{min_x:.1f}",
            cy=f"{min_y:.1f}",
            badge_left_pct=min_left,
            badge_top_pct=min_top,
            badge_tx=min_tx,
            badge_text=f"↓ 最低 {min_val} · {datetime.fromtimestamp(min_at).strftime('%m-%d %H:%M')}",
        ),
        match_count=len(coords),
        tier_label=tier_label,
        tier_color=tier_color,
        score_text=score_text,
        range_tier_label=range_tier_label,
        range_score_text=range_score_text,
        net_class=net_class,
        net_text=net_text,
        wins=wins,
        losses=losses,
        draws=draws,
    )


def render_empty_summary_html(message: str) -> str:
    """没有本地战绩时显示的最小卡片，避免输出空图片。"""
    return render_template(
        "empty_summary_card.html",
        EmptySummaryTemplateContext(message=message),
    )


async def render_empty_summary_card(message: str) -> bytes:
    """把空战绩提示渲染成 PNG 卡片。"""
    return await render_card(
        "empty_summary_card.html",
        EmptySummaryTemplateContext(message=message),
        width=CARD_WIDTH,
        default_font_size=15,
    )


def _build_role_item(role: DakanuRole, image: str, max_count: int) -> RoleItem:
    meta = resolve_role_meta(role.roleId)
    bar_pct = max(4, round(role.count / max(1, max_count) * 100))
    return RoleItem(
        image=image,
        name=role.name,
        faction_name=meta.faction_name if meta is not None else "",
        faction_color=meta.faction_text_color if meta is not None else "",
        position_name=meta.position_name if meta is not None else "",
        win_rate=_pct(role.winRate),
        count=role.count,
        kd=f"{role.kd:.2f}",
        avg_damage=_num(role.avgDamage),
        max_kill=role.maxKill,
        bar_pct=str(bar_pct),
    )


def _build_mode_item(mode: DakanuMode) -> ModeItem:
    return ModeItem(
        label=mode.label,
        rounds=mode.rounds,
        win_rate=_pct(mode.winRate),
        kd=f"{mode.kd:.2f}",
        avg_damage=_num(mode.avgDamage),
        round_avg_damage=f"{mode.roundAveDamage:.1f}",
        avg_kill=f"{mode.avgKill:.2f}",
        headshot_rate=_pct(mode.headshotRate),
        mvp_rate=_pct(mode.mvpRate),
    )


def _build_challenge_block(assets: SummaryAssets, presence: DakanuPresence) -> ChallengeBlock | None:
    leisure = assets.leisure
    score = 0
    segment = 0
    has_detail = False
    win_rate = 0.0
    star = 0
    star_score = 0
    if leisure is not None:
        if leisure.score is not None:
            score = leisure.score
        if leisure.segment is not None:
            segment = leisure.segment
        if leisure.star is not None:
            star = leisure.star
        if leisure.starScore is not None:
            star_score = leisure.starScore
        if leisure.winRate is not None:
            win_rate = float(leisure.winRate)
        has_detail = leisure.battles is not None
    elif assets.is_season_view:
        return None
    else:
        if presence.leisureScore is not None:
            score = presence.leisureScore
        if presence.leisureSegment is not None:
            segment = presence.leisureSegment
        if presence.stars is not None:
            star = presence.stars

    if segment <= 0 and score > 0:
        segment = _challenge_segment_from_score(score)
    if segment < 1 or segment > 41:
        return None

    challenge_name, challenge_color, tier_idx = challenge_tier_display(segment)
    if not challenge_name:
        return None
    tier_entry = _CHALLENGE_TABLE[tier_idx - 1]
    divisions = tier_entry[5]
    if not divisions:
        progress_label = "最高段位"
        progress_text = f"{_num(score)} 分"
        progress_pct = "100"
    else:
        _, d_from, d_to, req_stars = divisions[(segment - 1) % 5]
        if leisure is not None and leisure.starScore is not None:
            progress_label = "星级进展"
            progress_text = f"{star_score} / {req_stars}"
            progress_pct = str(max(0, min(100, round(star_score / max(1, req_stars) * 100))))
        else:
            progress_label = "段位分进度"
            progress_text = f"{_num(score)} / {_num(d_to + 1)}"
            progress_pct = str(max(0, min(100, round((score - d_from) / max(1, d_to - d_from + 1) * 100))))
    return ChallengeBlock(
        icon=assets.challenge_icon,
        name=challenge_name,
        color=challenge_color,
        score=score,
        win_rate=_pct(win_rate),
        star=star,
        has_detail=has_detail,
        progress_label=progress_label,
        progress_text=progress_text,
        progress_pct=progress_pct,
    )


def _build_medals(player: DakanuPlayer, medal_images: Mapping[int, str]) -> tuple[MedalItem, ...]:
    raw_medals = player.medals
    parsed: list[tuple[int, list[int] | None, float, float, bool]] = []
    for item in raw_medals:
        if isinstance(item, int):
            mid = item
            axis: list[int] | None = None
            zoom = 1.0
            rot = 0.0
            flip = False
        elif isinstance(item, DakanuMedal) and item.id is not None:
            mid = item.id
            axis = item.axis if item.axis is not None and len(item.axis) >= 2 else None
            zoom = item.zoomScale if item.zoomScale is not None and item.zoomScale > 0 else 1.0
            rot = item.rotateScale if item.rotateScale is not None else 0.0
            flip = item.levelFlip
        else:
            continue
        if mid in medal_images and medal_images[mid]:
            parsed.append((mid, axis, zoom, rot, flip))

    unplaced = [entry for entry in parsed if entry[1] is None]
    result: list[MedalItem] = []
    for entry in parsed:
        mid, axis, zoom, rot, flip = entry
        width_pct = 64.0 * zoom * 100.0 / 504.0
        if axis is not None:
            left_pct = 50.0 + 100.0 * float(axis[0]) / 504.0
            top_pct = 50.0 + 100.0 * float(axis[1]) / 1224.0
        else:
            idx = unplaced.index(entry)
            step = 26.0 if len(unplaced) > 1 else 0.0
            left_pct = 50.0 + (idx - (len(unplaced) - 1) / 2.0) * step
            top_pct = 84.0
        sx = -1 if flip else 1
        result.append(
            MedalItem(
                image=medal_images[mid],
                left_pct=f"{left_pct:.2f}%",
                top_pct=f"{top_pct:.2f}%",
                width_pct=f"{width_pct:.2f}%",
                transform=f"translate(-50%, -50%) rotate({rot:.1f}deg) scale({sx}, 1)",
            )
        )
    return tuple(result)


def _build_ranked_strip(modes: list[DakanuMode]) -> RankedStripBlock | None:
    active = [mode for mode in modes if mode.rounds > 0]
    if not active:
        return None
    target = next((mode for mode in active if mode.mode == "RoomMode_RANK_BOMB"), None)
    if target is None:
        bomb_modes = [mode for mode in active if "BOMB" in mode.mode.upper() and "ZOMBIE" not in mode.mode.upper()]
        if bomb_modes:
            target = max(bomb_modes, key=lambda item: item.rounds)
    if target is None:
        return None
    if target.kda is not None:
        kda_val = float(target.kda)
    else:
        kda_val = target.kd
    return RankedStripBlock(
        rounds=target.rounds,
        wins=target.wins,
        win_rate=_pct(target.winRate),
        kda=f"{kda_val:.2f}",
        kd=f"{target.kd:.2f}",
        round_avg_damage=f"{target.roundAveDamage:.1f}",
    )


def _build_recent_form(profile: DakanuProfile, role_images: Mapping[int, str]) -> RecentFormBlock:
    recent = profile.matches[:_RECENT_FORM_LIMIT]
    valid = [match for match in recent if match.result != "unknown"]
    if not valid:
        return RecentFormBlock(
            has_data=False,
            games=0,
            wins=0,
            losses=0,
            draws=0,
            win_rate_pct=0,
            win_rate_text="0%",
            avg_kda_line="",
            kda_ratio="",
            kill_participation="—",
            top_roles=(),
            positions=(),
        )
    wins = sum(1 for match in valid if match.result == "win")
    losses = sum(1 for match in valid if match.result == "lose")
    draws = sum(1 for match in valid if match.result == "draw")
    games = len(valid)
    win_rate_pct = round(wins / games * 100)
    kda_matches = [
        match for match in recent if match.kills is not None and match.deaths is not None and match.assists is not None
    ]
    total_k = sum(match.kills for match in kda_matches if match.kills is not None)
    total_d = sum(match.deaths for match in kda_matches if match.deaths is not None)
    total_a = sum(match.assists for match in kda_matches if match.assists is not None)
    total_tk = sum(match.teamKills for match in kda_matches if match.teamKills is not None)
    kda_ratio = (total_k + total_a) / total_d if total_d > 0 else float(total_k + total_a)
    kp_text = f"{round((total_k + total_a) / total_tk * 100)}%" if total_tk > 0 else "—"
    match_denom = max(1, len(kda_matches))
    avg_kda_line = (
        f"{total_k / match_denom:.1f} / {total_d / match_denom:.1f} / {total_a / match_denom:.1f}"
        if kda_matches
        else "— / — / —"
    )

    role_names_map: dict[int, str] = dict(get_role_display_names())
    for role in profile.roles:
        role_names_map[role.roleId] = role.name

    role_agg: dict[int, dict[str, int]] = {}
    pos_counts: dict[int, int] = {code: 0 for code in ROLE_POSITIONS}
    for match in recent:
        rid = match.roleId
        if rid is None or rid <= 0:
            continue
        if rid not in role_agg:
            role_agg[rid] = {"games": 0, "wins": 0, "losses": 0, "draws": 0, "k": 0, "d": 0, "a": 0}
        bucket = role_agg[rid]
        bucket["games"] += 1
        if match.result == "win":
            bucket["wins"] += 1
        elif match.result == "lose":
            bucket["losses"] += 1
        elif match.result == "draw":
            bucket["draws"] += 1
        if match.kills is not None:
            bucket["k"] += match.kills
        if match.deaths is not None:
            bucket["d"] += match.deaths
        if match.assists is not None:
            bucket["a"] += match.assists
        meta = resolve_role_meta(rid)
        if meta is not None and meta.position_code in pos_counts:
            pos_counts[meta.position_code] += 1

    sorted_roles = sorted(
        role_agg.items(),
        key=lambda item: (item[1]["games"], item[1]["wins"] / max(1, item[1]["games"])),
        reverse=True,
    )[:3]
    top_roles: list[RecentRoleItem] = []
    for rid, stat in sorted_roles:
        r_name = role_names_map[rid] if rid in role_names_map else f"角色 {rid}"
        r_img = role_images[rid] if rid in role_images else ""
        r_kda = (stat["k"] + stat["a"]) / stat["d"] if stat["d"] > 0 else float(stat["k"] + stat["a"])
        draw_part = f"{stat['draws']}平" if stat["draws"] > 0 else ""
        r_rate = f"{round(stat['wins'] / max(1, stat['games']) * 100)}%"
        top_roles.append(
            RecentRoleItem(
                image=r_img,
                name=r_name,
                record_text=f"{stat['wins']}胜{stat['losses']}负{draw_part}",
                win_rate=r_rate,
                kda=f"{r_kda:.2f}",
            )
        )

    max_pos = max(1, *pos_counts.values())
    positions = tuple(
        PositionDistItem(
            name=ROLE_POSITIONS[code],
            count=cnt,
            bar_pct=str(max(8, round(cnt / max_pos * 100))) if cnt > 0 else "0",
        )
        for code, cnt in sorted(pos_counts.items(), key=lambda item: item[1], reverse=True)
    )
    return RecentFormBlock(
        has_data=True,
        games=games,
        wins=wins,
        losses=losses,
        draws=draws,
        win_rate_pct=win_rate_pct,
        win_rate_text=f"{win_rate_pct}%",
        avg_kda_line=avg_kda_line,
        kda_ratio=f"{kda_ratio:.2f}",
        kill_participation=kp_text,
        top_roles=tuple(top_roles),
        positions=positions,
    )


def _build_activity_hours(matches: list[DakanuMatch]) -> ActivityHoursBlock:
    counts = [0] * 24
    sample = 0
    for match in matches[:_ACTIVITY_HOURS_LIMIT]:
        played_at = match.playedAt
        if played_at > 0:
            counts[datetime.fromtimestamp(played_at).hour] += 1
            sample += 1
    if sample == 0:
        return ActivityHoursBlock(
            has_data=False,
            sample_count=0,
            peak_text="—",
            morning_cells=(),
            afternoon_cells=(),
        )
    max_count = max(1, *counts)
    cells = [
        HourCellItem(
            hour_label=f"{hour:02d}",
            level=0 if cnt == 0 else max(1, math.ceil(cnt / max_count * 4)),
        )
        for hour, cnt in enumerate(counts)
    ]
    peak_hour = max(range(24), key=lambda h: counts[h])
    peak_text = f"{peak_hour:02d}:00 ({counts[peak_hour]} 场)"
    return ActivityHoursBlock(
        has_data=True,
        sample_count=sample,
        peak_text=peak_text,
        morning_cells=tuple(cells[:12]),
        afternoon_cells=tuple(cells[12:]),
    )


def _season_started_at(profile: DakanuProfile) -> int | None:
    started_at = profile.meta.currentSeasonStartedAt
    if started_at is not None and started_at > 0:
        return started_at
    return None


def select_current_season_matches(
    profile: DakanuProfile,
    limit: int = _SEASON_RECENT_MATCHES_LIMIT,
) -> list[DakanuMatch]:
    """按当前赛季开赛时间筛选最近对局；缺失开赛时间时返回空列表。"""
    started_at = _season_started_at(profile)
    if started_at is None:
        return []
    seen_rooms: set[str] = set()
    candidates: list[DakanuMatch] = []
    for match in profile.matches:
        if match.playedAt is None or match.playedAt < started_at:
            continue
        room_id = match.roomId
        if room_id in seen_rooms:
            continue
        seen_rooms.add(room_id)
        candidates.append(match)
    candidates.sort(key=lambda item: item.playedAt or 0, reverse=True)
    return candidates[:limit]


def _build_recent_matches(
    assets: SummaryAssets,
) -> tuple[MatchCardItem, ...]:
    if not assets.recent_match_views:
        return ()
    match_assets = MatchCardAssets(
        player_avatar=assets.avatar,
        avatar_images=assets.avatar_images,
        role_images=assets.role_images,
        map_images=assets.map_images,
        clan_name=assets.clan_name,
    )
    return tuple(build_match_card_item(view, match_assets) for view in assets.recent_match_views)


def _build_team_ups(profile: DakanuProfile, avatar_images: Mapping[int, str]) -> tuple[RelationshipItem, ...]:
    items: list[RelationshipItem] = []
    entries: list[DakanuTeamUp] = profile.teamUps[:5]
    for entry in entries:
        aid = entry.avatarId
        avatar = avatar_images[aid] if aid in avatar_images else ""
        draw_part = f" {entry.teamedDraws}平" if entry.teamedDraws > 0 else ""
        items.append(
            RelationshipItem(
                avatar=avatar,
                initial=entry.nickname[:1] or "?",
                nickname=entry.nickname,
                meta_text=f"同队 {entry.teamedGames} 场 · {entry.teamedWins}胜 {entry.teamedLosses}负{draw_part}",
                win_rate=_pct(entry.teamedWinRate),
            )
        )
    return tuple(items)


def _build_rivals(profile: DakanuProfile, avatar_images: Mapping[int, str]) -> tuple[RelationshipItem, ...]:
    items: list[RelationshipItem] = []
    entries: list[DakanuRival] = profile.rivals[:5]
    for entry in entries:
        aid = entry.avatarId
        avatar = avatar_images[aid] if aid in avatar_images else ""
        draw_part = f" {entry.draws}平" if entry.draws > 0 else ""
        items.append(
            RelationshipItem(
                avatar=avatar,
                initial=entry.nickname[:1] or "?",
                nickname=entry.nickname,
                meta_text=f"交锋 {entry.games} 场 · {entry.wins}胜 {entry.losses}负{draw_part}",
                win_rate=_pct(entry.winRate),
            )
        )
    return tuple(items)


def _build_presence_line(presence: DakanuPresence) -> tuple[str, bool]:
    state = presence.state
    is_online = state in {"online", "busy", "invisible"}
    label = _PRESENCE_LABELS[state] if state in _PRESENCE_LABELS else state or "未知"
    last_at = presence.lastOnlineAt if presence.lastOnlineAt is not None else presence.lastActiveAt
    if not is_online and last_at is not None and last_at > 0:
        return f"{label} · 上次在线 {datetime.fromtimestamp(last_at).strftime('%m-%d %H:%M')}", False
    return label, is_online


def _build_summary_context(profile: DakanuProfile, assets: SummaryAssets) -> SummaryTemplateContext:
    player = profile.player
    presence = profile.presence
    rank = profile.rank
    summary: DakanuSummary = profile.summary
    tier_label, tier_color, _ = _tier(rank.segment)
    season_top_seg = max(rank.topSegment, rank.segment)
    season_top_label, _, _ = _tier(season_top_seg)
    top_label, top_color, _ = _tier(rank.historicalSegment)
    privacy_status = player.privacyStatus
    privacy_label = _PRIVACY_LABELS[privacy_status] if privacy_status in _PRIVACY_LABELS else "隐私未知"
    verify_label = "已认证" if player.accountVerified else "历史未校验"
    previous = "、".join(player.previousNames[:2]) or "无"
    rank_pos = f"#{rank.rankPos}" if rank.rankPos is not None else "未上榜"
    historical_pos = str(rank.historicalSegmentPos) if rank.historicalSegmentPos is not None else "—"
    bar_width = max(0.0, min(100.0, summary.winRate * 100))
    region_label = presence.regionLabel if presence.regionLabel else ""
    presence_text, presence_online = _build_presence_line(presence)

    grade_score = rank.gradeScore
    top_grade_score = rank.topGradeScore
    if rank.divisionScore > 0:
        score_sub_text = f"{rank.divisionScore} 段位分"
    elif grade_score > 0:
        score_sub_text = f"段位分 0 · 积分 {grade_score}"
    else:
        score_sub_text = "0 段位分"
    if rank.topDivisionScore > 0:
        top_score_sub_text = f"{rank.topDivisionScore} 历史段位分"
    elif top_grade_score > 0:
        top_score_sub_text = f"最高积分 {top_grade_score}"
    else:
        top_score_sub_text = "0 历史段位分"

    top_roles_raw = profile.roles[:5]
    max_role_count = max((role.count for role in top_roles_raw), default=1)
    roles = tuple(
        _build_role_item(
            role,
            assets.role_images[role.roleId] if role.roleId in assets.role_images else "",
            max_role_count,
        )
        for role in top_roles_raw
    )
    modes = tuple(_build_mode_item(mode) for mode in profile.modes[:3])
    total_damage = _num(summary.damage)

    return SummaryTemplateContext(
        nickname=player.nickname,
        uid=player.id,
        season=profile.meta.currentSeason,
        is_season_view=assets.is_season_view,
        avatar=assets.avatar,
        avatar_frame=assets.avatar_frame,
        region_label=region_label,
        presence_text=presence_text,
        presence_online=presence_online,
        privacy_label=privacy_label,
        verify_label=verify_label,
        clan_name=assets.clan_name,
        level=player.level,
        laud=player.laud,
        previous_names=previous,
        like_count=rank.likeCount,
        tier_icon=assets.tier_icon,
        tier_label=tier_label,
        tier_color=tier_color,
        score_sub_text=score_sub_text,
        rank_pos=rank_pos,
        season_top_label=season_top_label,
        historical_season=rank.historicalSegmentSeason,
        top_tier_icon=assets.top_tier_icon,
        top_label=top_label,
        top_color=top_color,
        top_score_sub_text=top_score_sub_text,
        historical_pos=historical_pos,
        challenge=_build_challenge_block(assets, presence),
        baseplate=assets.baseplate,
        frame=assets.frame,
        medals=_build_medals(player, assets.medal_images),
        rounds=summary.rounds,
        wins=summary.wins,
        losses=summary.losses,
        win_rate_text=_pct(summary.winRate),
        bar_width_pct=f"{bar_width:.1f}",
        kills=summary.kills,
        deaths=summary.deaths,
        assists=summary.assists,
        kd_text=f"{summary.kd:.2f}",
        kda_text=f"{summary.kda:.2f}",
        total_damage=total_damage,
        avg_damage=_num(summary.avgDamage),
        round_avg_damage=f"{summary.roundAveDamage:.1f}",
        avg_kill=f"{summary.avgKill:.2f}",
        avg_death=f"{summary.avgDeath:.2f}",
        avg_assist=f"{summary.avgAssist:.2f}",
        headshot_rate=_pct(summary.headshotRate),
        mvp_rate=_pct(summary.mvpRate),
        mvp_count=summary.mvpCount,
        ranked_strip=_build_ranked_strip(profile.modes),
        recent_form=None if assets.is_season_view else _build_recent_form(profile, assets.role_images),
        trend=None if assets.is_season_view else _build_trend(profile),
        activity_hours=None if assets.is_season_view else _build_activity_hours(profile.matches),
        roles=roles,
        modes=modes,
        recent_matches=() if assets.is_season_view else _build_recent_matches(assets),
        team_ups=() if assets.is_season_view else _build_team_ups(profile, assets.avatar_images),
        rivals=() if assets.is_season_view else _build_rivals(profile, assets.avatar_images),
    )


def render_summary_html(profile: DakanuProfile, assets: SummaryAssets) -> str:
    """生成战绩总览完整 HTML 文档。"""
    return render_template("summary_card.html", _build_summary_context(profile, assets))


async def render_summary_card(profile: DakanuProfile, assets: SummaryAssets) -> bytes:
    """把总览数据渲染成 PNG 卡片。"""
    return await render_card(
        "summary_card.html",
        _build_summary_context(profile, assets),
        width=CARD_WIDTH,
        default_font_size=15,
    )
