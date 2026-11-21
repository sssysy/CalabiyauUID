"""排位段位榜 HTML 卡片。"""

from dataclasses import dataclass
from collections.abc import Mapping

from ..render import CARD_WIDTH, CardTemplateContext, render_card, render_template
from .summary_card import tier_display, challenge_tier_display
from ....api.dakanu import DakanuRankingEntry, DakanuRankingFloor, DakanuRankingsBoard


@dataclass(frozen=True)
class RankingCardAssets:
    avatar_images: Mapping[int, str]
    role_images: Mapping[int, str]
    tier_images: Mapping[int, str]


@dataclass(frozen=True)
class FloorPillItem:
    score: str
    delta_text: str
    delta_class: str


@dataclass(frozen=True)
class PodiumCardItem:
    position: int
    rank_class: str
    is_first: bool
    avatar: str
    initial: str
    nickname: str
    tier_uri: str
    tier_label: str
    tier_color: str
    meta_text: str
    score: str
    is_long_score: bool
    roles: tuple[str, ...]


@dataclass(frozen=True)
class RankingRowItem:
    position: int
    avatar: str
    initial: str
    nickname: str
    player_id: str
    region_text: str
    tier_uri: str
    tier_label: str
    tier_color: str
    score: str
    delta_text: str
    delta_class: str
    roles: tuple[str, ...]
    has_record_bar: bool
    has_games: bool
    wins: int
    losses: int
    win_width_pct: str | None
    loss_width_pct: str | None
    win_rate_text: str
    wins_only_text: str


@dataclass(frozen=True)
class RankingTemplateContext(CardTemplateContext):
    title: str = "段位榜"
    metric_label: str = "段位分"
    record_header: str = "胜率"
    show_tier: bool = True
    compact_record: bool = False
    floor: FloorPillItem | None = None
    season_label: str = ""
    is_historical_season: bool = False
    has_entries: bool = False
    podium: tuple[PodiumCardItem, ...] = ()
    rows: tuple[RankingRowItem, ...] = ()


def _lookup_image(images: Mapping[int, str], key: int) -> str:
    return images[key] if key in images else ""


def _role_uris(roles: list[int], assets: RankingCardAssets) -> tuple[str, ...]:
    chips: list[str] = []
    for role_id in roles[:3]:
        uri = _lookup_image(assets.role_images, role_id)
        if uri:
            chips.append(uri)
    return tuple(chips)


def _delta_parts(score_delta: int | None) -> tuple[str, str]:
    if score_delta is None:
        return "—", "delta--flat"
    if score_delta > 0:
        return f"▲ {score_delta:,}", "delta--up"
    if score_delta < 0:
        return f"▼ {abs(score_delta):,}", "delta--down"
    return "0", "delta--flat"


def _build_floor_item(floor: DakanuRankingFloor | None) -> FloorPillItem | None:
    if floor is None:
        return None
    score = f"{floor['current']['score']:,}"
    delta = floor["yesterdayDelta"]
    if delta is None:
        return FloorPillItem(score=score, delta_text="", delta_class="")
    if delta > 0:
        return FloorPillItem(score=score, delta_text=f"↑ {delta:,}", delta_class="pill-delta--up")
    if delta < 0:
        return FloorPillItem(score=score, delta_text=f"↓ {abs(delta):,}", delta_class="pill-delta--down")
    return FloorPillItem(score=score, delta_text="0", delta_class="pill-delta--flat")


def _podium_order(top_entries: list[DakanuRankingEntry]) -> list[DakanuRankingEntry]:
    if len(top_entries) >= 3:
        return [top_entries[1], top_entries[0], top_entries[2]]
    return list(top_entries)


def _resolve_tier(segment: int | None, tier_mode: str, assets: RankingCardAssets) -> tuple[str, str, str]:
    if segment is None or tier_mode == "none":
        return "", "rgba(0, 0, 0, .42)", ""
    if tier_mode == "challenge":
        tier_label, tier_color, tier_idx = challenge_tier_display(segment)
    else:
        tier_label, tier_color, tier_idx = tier_display(segment)
    if not tier_label:
        return "", "rgba(0, 0, 0, .42)", ""
    tier_uri = _lookup_image(assets.tier_images, tier_idx) if tier_idx > 0 else ""
    return tier_label, tier_color, tier_uri


def _build_podium_item(entry: DakanuRankingEntry, assets: RankingCardAssets, tier_mode: str) -> PodiumCardItem:
    position = entry["position"]
    rank_class = f"podium-pos-{position}" if position in {1, 2, 3} else "podium-pos-other"
    tier_label, tier_color, tier_uri = _resolve_tier(entry["segment"], tier_mode, assets)
    region = entry["region"].strip() if entry["region"] is not None else ""
    meta_text = f"等级 {entry['level']} · {region}" if region else f"等级 {entry['level']}"
    score_text = f"{entry['score']:,}"
    return PodiumCardItem(
        position=position,
        rank_class=rank_class,
        is_first=position == 1,
        avatar=_lookup_image(assets.avatar_images, entry["avatarId"]),
        initial=entry["nickname"][0] if entry["nickname"] else "?",
        nickname=entry["nickname"],
        tier_uri=tier_uri,
        tier_label=tier_label,
        tier_color=tier_color,
        meta_text=meta_text,
        score=score_text,
        is_long_score=len(score_text) > 10,
        roles=_role_uris(entry["roles"], assets),
    )


def _build_row_item(entry: DakanuRankingEntry, assets: RankingCardAssets, tier_mode: str) -> RankingRowItem:
    tier_label, tier_color, tier_uri = _resolve_tier(entry["segment"], tier_mode, assets)
    region = entry["region"].strip() if entry["region"] is not None else ""
    region_text = region if region else "—"
    delta_text, delta_class = _delta_parts(entry["scoreDelta"])

    raw_wins = entry["wins"]
    raw_total_games = entry["totalGames"]
    wins = max(0, raw_wins) if raw_wins is not None else 0
    has_record_bar = raw_total_games is not None
    total_games = max(0, raw_total_games) if raw_total_games is not None else 0
    losses = max(0, total_games - wins)
    win_rate = (wins / total_games * 100.0) if total_games > 0 else 0.0
    has_games = wins > 0 or losses > 0
    win_width_pct: str | None = None
    loss_width_pct: str | None = None
    if has_record_bar and has_games:
        if losses == 0:
            win_width_pct = "100.0"
        elif wins == 0:
            loss_width_pct = "100.0"
        else:
            win_width = max(24.0, min(76.0, win_rate))
            loss_width = 100.0 - win_width
            win_width_pct = f"{win_width:.1f}"
            loss_width_pct = f"{loss_width:.1f}"

    wins_only_text = f"{wins:,} 胜" if raw_wins is not None else "—"

    return RankingRowItem(
        position=entry["position"],
        avatar=_lookup_image(assets.avatar_images, entry["avatarId"]),
        initial=entry["nickname"][0] if entry["nickname"] else "?",
        nickname=entry["nickname"],
        player_id=entry["playerId"],
        region_text=region_text,
        tier_uri=tier_uri,
        tier_label=tier_label if tier_label else "—",
        tier_color=tier_color,
        score=f"{entry['score']:,}",
        delta_text=delta_text,
        delta_class=delta_class,
        roles=_role_uris(entry["roles"], assets),
        has_record_bar=has_record_bar,
        has_games=has_games,
        wins=wins,
        losses=losses,
        win_width_pct=win_width_pct,
        loss_width_pct=loss_width_pct,
        win_rate_text=f"{win_rate:.0f}%",
        wins_only_text=wins_only_text,
    )


def _build_ranking_context(
    board: DakanuRankingsBoard,
    floor: DakanuRankingFloor | None,
    season_label: str,
    assets: RankingCardAssets,
    *,
    tier_mode: str = "ranked",
    title_override: str | None = None,
    is_historical_season: bool = False,
) -> RankingTemplateContext:
    entries = board["entries"]
    title = title_override if title_override else (board["rankType"]["label"] or "排行榜")
    metric_label = board["metricLabel"] or "分数"
    has_total_games = any(entry["totalGames"] is not None for entry in entries)
    record_header = "胜率" if has_total_games or not entries else "胜场"
    show_tier = tier_mode != "none"
    podium_entries = _podium_order(entries[:3])
    return RankingTemplateContext(
        title=title,
        metric_label=metric_label,
        record_header=record_header,
        show_tier=show_tier,
        compact_record=not has_total_games and bool(entries),
        floor=_build_floor_item(floor),
        season_label=season_label,
        is_historical_season=is_historical_season,
        has_entries=bool(entries),
        podium=tuple(_build_podium_item(entry, assets, tier_mode) for entry in podium_entries),
        rows=tuple(_build_row_item(entry, assets, tier_mode) for entry in entries[3:]),
    )


def render_ranking_html(
    board: DakanuRankingsBoard,
    floor: DakanuRankingFloor | None,
    season_label: str,
    assets: RankingCardAssets,
    *,
    tier_mode: str = "ranked",
    title_override: str | None = None,
    is_historical_season: bool = False,
) -> str:
    """生成排行榜完整 HTML 文档。"""
    context = _build_ranking_context(
        board,
        floor,
        season_label,
        assets,
        tier_mode=tier_mode,
        title_override=title_override,
        is_historical_season=is_historical_season,
    )
    return render_template("ranking_card.html", context)


async def render_ranking_card(
    board: DakanuRankingsBoard,
    floor: DakanuRankingFloor | None,
    season_label: str,
    assets: RankingCardAssets,
    *,
    tier_mode: str = "ranked",
    title_override: str | None = None,
    is_historical_season: bool = False,
) -> bytes:
    """把排行榜渲染成 PNG 卡片。"""
    context = _build_ranking_context(
        board,
        floor,
        season_label,
        assets,
        tier_mode=tier_mode,
        title_override=title_override,
        is_historical_season=is_historical_season,
    )
    return await render_card(
        "ranking_card.html",
        context,
        width=CARD_WIDTH,
        default_font_size=14,
    )
