"""战绩总览静态卡片。"""

from dataclasses import dataclass

from .render import CARD_WIDTH, CardTemplateContext, render_card, render_template
from ...api.dakanu import DakanuMode, DakanuRole, DakanuMatch, DakanuLeisure, DakanuProfile, DakanuSummary

_TREND_POINTS = 12
_PRIVACY_LABELS = {
    "open": "生涯公开",
    "hidden": "生涯隐藏",
    "unavailable": "不可查询",
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


@dataclass(frozen=True)
class SummaryAssets:
    avatar: str
    tier_icon: str
    top_tier_icon: str
    challenge_icon: str
    baseplate: str
    frame: str
    role_images: tuple[str, ...]
    clan_name: str
    leisure: DakanuLeisure | None


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


@dataclass(frozen=True)
class TrendDot:
    x: str
    y: str


@dataclass(frozen=True)
class TrendBlock:
    has_chart: bool
    svg_area: str
    svg_line: str
    dots: tuple[TrendDot, ...]
    match_count: int
    tier_label: str
    tier_color: str
    division_score: int
    net_class: str
    net_text: str
    wins: int
    losses: int
    draws: int


@dataclass(frozen=True)
class RoleItem:
    image: str
    name: str
    win_rate: str
    count: int
    kd: str


@dataclass(frozen=True)
class ModeItem:
    label: str
    rounds: int
    win_rate: str
    kd: str
    avg_damage: str
    avg_kill: str
    headshot_rate: str
    mvp_rate: str


@dataclass(frozen=True)
class SummaryTemplateContext(CardTemplateContext):
    nickname: str = ""
    uid: str = ""
    season: str = ""
    avatar: str = ""
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
    division_score: int = 0
    rank_pos: str = ""
    historical_season: int = 0
    top_tier_icon: str = ""
    top_label: str = ""
    top_color: str = ""
    top_division_score: int = 0
    historical_pos: str = "—"
    challenge: ChallengeBlock | None = None
    baseplate: str = ""
    frame: str = ""
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
    avg_damage: str = ""
    round_avg_damage: str = ""
    avg_kill: str = ""
    avg_death: str = ""
    avg_assist: str = ""
    headshot_rate: str = ""
    mvp_rate: str = ""
    mvp_count: int = 0
    trend: TrendBlock | None = None
    roles: tuple[RoleItem, ...] = ()
    modes: tuple[ModeItem, ...] = ()


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


def _trend_matches(profile: DakanuProfile) -> list[DakanuMatch]:
    ranked = [
        match for match in profile["historyMatches"] if "RANK" in match["mode"] and match["divisionScore"] is not None
    ]
    return list(reversed(ranked))[-_TREND_POINTS:]


def _build_trend(profile: DakanuProfile) -> TrendBlock:
    matches = _trend_matches(profile)
    rank = profile["rank"]
    scores = [match["divisionScore"] for match in matches if match["divisionScore"] is not None]
    net = scores[-1] - scores[0] if len(scores) >= 2 else 0
    wins = sum(1 for match in matches if match["result"] == "win")
    losses = sum(1 for match in matches if match["result"] == "lose")
    draws = sum(1 for match in matches if match["result"] == "draw")
    tier_label, tier_color, _ = _tier(rank["segment"])
    net_class = "is-up" if net >= 0 else "is-down"
    net_text = f"+{net}" if net >= 0 else str(net)

    svg_line = ""
    svg_area = ""
    dots: list[TrendDot] = []
    has_chart = len(matches) >= 2 and len(scores) >= 2
    if has_chart:
        low, high = min(scores), max(scores)
        span = max(1, high - low)
        points: list[str] = []
        for index, score in enumerate(scores):
            x_pos = 12 + index * (336 / (len(scores) - 1))
            y_pos = 128 - ((score - low) / span) * 92
            x_text = f"{x_pos:.1f}"
            y_text = f"{y_pos:.1f}"
            points.append(f"{x_text},{y_text}")
            dots.append(TrendDot(x=x_text, y=y_text))
        svg_line = " ".join(points)
        svg_area = f"12,142 {svg_line} 348,142"

    return TrendBlock(
        has_chart=has_chart,
        svg_area=svg_area,
        svg_line=svg_line,
        dots=tuple(dots),
        match_count=len(matches),
        tier_label=tier_label,
        tier_color=tier_color,
        division_score=rank["divisionScore"],
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


def _build_role_item(role: DakanuRole, image: str) -> RoleItem:
    return RoleItem(
        image=image,
        name=role["name"],
        win_rate=_pct(role["winRate"]),
        count=role["count"],
        kd=f"{role['kd']:.2f}",
    )


def _build_mode_item(mode: DakanuMode) -> ModeItem:
    return ModeItem(
        label=mode["label"],
        rounds=mode["rounds"],
        win_rate=_pct(mode["winRate"]),
        kd=f"{mode['kd']:.2f}",
        avg_damage=_num(mode["avgDamage"]),
        avg_kill=f"{mode['avgKill']:.2f}",
        headshot_rate=_pct(mode["headshotRate"]),
        mvp_rate=_pct(mode["mvpRate"]),
    )


def _build_challenge_block(assets: SummaryAssets) -> ChallengeBlock | None:
    leisure = assets.leisure
    if leisure is None or "segment" not in leisure:
        return None
    challenge_name, challenge_color = _challenge_label(leisure["segment"])
    challenge_score = leisure["score"] if "score" in leisure else 0
    challenge_rate = leisure["winRate"] if "winRate" in leisure else 0.0
    challenge_star = leisure["star"] if "star" in leisure else 0
    return ChallengeBlock(
        icon=assets.challenge_icon,
        name=challenge_name,
        color=challenge_color,
        score=challenge_score,
        win_rate=_pct(challenge_rate),
        star=challenge_star,
    )


def _build_summary_context(profile: DakanuProfile, assets: SummaryAssets) -> SummaryTemplateContext:
    player = profile["player"]
    rank = profile["rank"]
    summary: DakanuSummary = profile["summary"]
    tier_label, tier_color, _ = _tier(rank["segment"])
    top_label, top_color, _ = _tier(rank["topSegment"])
    privacy_status = player["privacyStatus"]
    privacy_label = _PRIVACY_LABELS[privacy_status] if privacy_status in _PRIVACY_LABELS else "隐私未知"
    verify_label = "已认证" if player["accountVerified"] else "历史未校验"
    previous = "、".join(player["previousNames"][:2]) or "无"
    rank_pos = f"#{rank['rankPos']}" if rank["rankPos"] is not None else "未上榜"
    historical_pos = str(rank["historicalSegmentPos"]) if rank["historicalSegmentPos"] is not None else "—"
    bar_width = max(0.0, min(100.0, summary["winRate"] * 100))

    role_images = assets.role_images
    roles = tuple(
        _build_role_item(role, role_images[index] if index < len(role_images) else "")
        for index, role in enumerate(profile["roles"][:5])
    )
    modes = tuple(_build_mode_item(mode) for mode in profile["modes"][:3])

    return SummaryTemplateContext(
        nickname=player["nickname"],
        uid=player["id"],
        season=profile["meta"]["currentSeason"],
        avatar=assets.avatar,
        privacy_label=privacy_label,
        verify_label=verify_label,
        clan_name=assets.clan_name,
        level=player["level"],
        laud=player["laud"],
        previous_names=previous,
        like_count=rank["likeCount"],
        tier_icon=assets.tier_icon,
        tier_label=tier_label,
        tier_color=tier_color,
        division_score=rank["divisionScore"],
        rank_pos=rank_pos,
        historical_season=rank["historicalSegmentSeason"],
        top_tier_icon=assets.top_tier_icon,
        top_label=top_label,
        top_color=top_color,
        top_division_score=rank["topDivisionScore"],
        historical_pos=historical_pos,
        challenge=_build_challenge_block(assets),
        baseplate=assets.baseplate,
        frame=assets.frame,
        rounds=summary["rounds"],
        wins=summary["wins"],
        losses=summary["losses"],
        win_rate_text=_pct(summary["winRate"]),
        bar_width_pct=f"{bar_width:.1f}",
        kills=summary["kills"],
        deaths=summary["deaths"],
        assists=summary["assists"],
        kd_text=f"{summary['kd']:.2f}",
        kda_text=f"{summary['kda']:.2f}",
        avg_damage=_num(summary["avgDamage"]),
        round_avg_damage=f"{summary['roundAveDamage']:.1f}",
        avg_kill=f"{summary['avgKill']:.2f}",
        avg_death=f"{summary['avgDeath']:.2f}",
        avg_assist=f"{summary['avgAssist']:.2f}",
        headshot_rate=_pct(summary["headshotRate"]),
        mvp_rate=_pct(summary["mvpRate"]),
        mvp_count=summary["mvpCount"],
        trend=_build_trend(profile),
        roles=roles,
        modes=modes,
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
