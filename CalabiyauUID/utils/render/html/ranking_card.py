"""排位段位榜 HTML 卡片。"""

from dataclasses import dataclass
from collections.abc import Mapping

from .render import CARD_WIDTH, CardTemplateContext, render_card, render_template
from ...api.dakanu import DakanuRankingEntry, DakanuRankingFloor, DakanuRankingsBoard
from .summary_card import tier_display


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
    has_games: bool
    wins: int
    losses: int
    win_width_pct: str | None
    loss_width_pct: str | None
    win_rate_text: str


@dataclass(frozen=True)
class RankingTemplateContext(CardTemplateContext):
    title: str = "段位榜"
    floor: FloorPillItem | None = None
    season_label: str = ""
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


def _build_podium_item(entry: DakanuRankingEntry, assets: RankingCardAssets) -> PodiumCardItem:
    position = entry["position"]
    rank_class = f"podium-pos-{position}" if position in {1, 2, 3} else "podium-pos-other"
    tier_label, tier_color, tier_idx = tier_display(entry["segment"])
    tier_uri = _lookup_image(assets.tier_images, tier_idx) if tier_idx > 0 else ""
    region = entry["region"].strip() if entry["region"] is not None else ""
    meta_text = f"等级 {entry['level']} · {region}" if region else f"等级 {entry['level']}"
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
        score=f"{entry['score']:,}",
        roles=_role_uris(entry["roles"], assets),
    )


def _build_row_item(entry: DakanuRankingEntry, assets: RankingCardAssets) -> RankingRowItem:
    tier_label, tier_color, tier_idx = tier_display(entry["segment"])
    tier_uri = _lookup_image(assets.tier_images, tier_idx) if tier_idx > 0 else ""
    region = entry["region"].strip() if entry["region"] is not None else ""
    region_text = region if region else "—"
    delta_text, delta_class = _delta_parts(entry["scoreDelta"])

    wins = max(0, entry["wins"])
    total_games = max(0, entry["totalGames"])
    losses = max(0, total_games - wins)
    win_rate = (wins / total_games * 100.0) if total_games > 0 else 0.0
    has_games = wins > 0 or losses > 0
    win_width_pct: str | None = None
    loss_width_pct: str | None = None
    if not has_games:
        pass
    elif losses == 0:
        win_width_pct = "100.0"
    elif wins == 0:
        loss_width_pct = "100.0"
    else:
        win_width = max(24.0, min(76.0, win_rate))
        loss_width = 100.0 - win_width
        win_width_pct = f"{win_width:.1f}"
        loss_width_pct = f"{loss_width:.1f}"

    return RankingRowItem(
        position=entry["position"],
        avatar=_lookup_image(assets.avatar_images, entry["avatarId"]),
        initial=entry["nickname"][0] if entry["nickname"] else "?",
        nickname=entry["nickname"],
        player_id=entry["playerId"],
        region_text=region_text,
        tier_uri=tier_uri,
        tier_label=tier_label,
        tier_color=tier_color,
        score=f"{entry['score']:,}",
        delta_text=delta_text,
        delta_class=delta_class,
        roles=_role_uris(entry["roles"], assets),
        has_games=has_games,
        wins=wins,
        losses=losses,
        win_width_pct=win_width_pct,
        loss_width_pct=loss_width_pct,
        win_rate_text=f"{win_rate:.0f}%",
    )


def _build_ranking_context(
    board: DakanuRankingsBoard,
    floor: DakanuRankingFloor | None,
    season_label: str,
    assets: RankingCardAssets,
) -> RankingTemplateContext:
    entries = board["entries"]
    title = board["rankType"]["label"] or "段位榜"
    podium_entries = _podium_order(entries[:3])
    return RankingTemplateContext(
        title=title,
        floor=_build_floor_item(floor),
        season_label=season_label,
        has_entries=bool(entries),
        podium=tuple(_build_podium_item(entry, assets) for entry in podium_entries),
        rows=tuple(_build_row_item(entry, assets) for entry in entries[3:]),
    )


def render_ranking_html(
    board: DakanuRankingsBoard,
    floor: DakanuRankingFloor | None,
    season_label: str,
    assets: RankingCardAssets,
) -> str:
    """生成排位排行榜完整 HTML 文档。"""
    return render_template("ranking_card.html", _build_ranking_context(board, floor, season_label, assets))


async def render_ranking_card(
    board: DakanuRankingsBoard,
    floor: DakanuRankingFloor | None,
    season_label: str,
    assets: RankingCardAssets,
) -> bytes:
    """把排位排行榜渲染成 PNG 卡片。"""
    return await render_card(
        "ranking_card.html",
        _build_ranking_context(board, floor, season_label, assets),
        width=CARD_WIDTH,
        default_font_size=14,
    )
