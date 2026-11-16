"""超弦体登场率与胜率排行榜 HTML 卡片。"""

from dataclasses import dataclass
from collections.abc import Mapping

from ..render import CARD_WIDTH, CardTemplateContext, render_card, render_template
from ....api.dakanu import DakanuRolesRankingBoard, DakanuRolesRankingEntry
from ....helper.maps import resolve_role_meta


@dataclass(frozen=True)
class RolesRankingRowItem:
    position: int
    rank_class: str
    portrait: str
    initial: str
    name: str
    faction_name: str
    faction_dot_color: str
    faction_text_color: str
    position_name: str
    has_meta_tag: bool
    appearance_rate_text: str
    appearance_delta_text: str
    appearance_delta_class: str
    win_rate_text: str
    win_delta_text: str
    win_delta_class: str
    games_text: str
    wins_text: str
    players_text: str


@dataclass(frozen=True)
class RolesRankingTemplateContext(CardTemplateContext):
    title: str = "超弦体登场率排行"
    scope_label: str = "仅排位"
    scope_class: str = "scope-ranked"
    covered_matches_text: str = "0 场"
    day_text: str = ""
    sort_by: str = "appearanceRate"
    has_entries: bool = False
    rows: tuple[RolesRankingRowItem, ...] = ()


def _format_rate_delta(delta: float | None) -> tuple[str, str]:
    if delta is None or abs(delta) < 0.0005:
        return "", ""
    pct = f"{abs(delta) * 100:.1f}%"
    if delta > 0:
        return f"▲ {pct}", "delta--up"
    return f"▼ {pct}", "delta--down"


def _rank_class(position: int) -> str:
    if position == 1:
        return "is-top1"
    if position == 2:
        return "is-top2"
    if position == 3:
        return "is-top3"
    return ""


def _sort_entries(
    entries: list[DakanuRolesRankingEntry],
    sort_by: str,
) -> list[DakanuRolesRankingEntry]:
    if sort_by == "winRate":
        return sorted(entries, key=lambda item: (item["winRate"], item["games"]), reverse=True)
    return sorted(entries, key=lambda item: (item["appearanceRate"], item["games"]), reverse=True)


def _resolve_role_meta(role_id: int) -> tuple[str, str, str, str, bool]:
    meta = resolve_role_meta(role_id)
    if meta is None:
        return "", "", "", "", False
    has_meta_tag = bool(meta.faction_name or meta.position_name)
    return (
        meta.faction_name,
        meta.faction_dot_color,
        meta.faction_text_color,
        meta.position_name,
        has_meta_tag,
    )


def _build_row_item(
    position: int,
    entry: DakanuRolesRankingEntry,
    role_names: Mapping[int, str],
    role_images: Mapping[int, str],
) -> RolesRankingRowItem:
    role_id = entry["roleId"]
    name = role_names[role_id] if role_id in role_names else f"角色 {role_id}"
    portrait = role_images[role_id] if role_id in role_images else ""
    faction_name, faction_dot_color, faction_text_color, position_name, has_meta_tag = _resolve_role_meta(role_id)
    app_delta_text, app_delta_class = _format_rate_delta(entry["appearanceRateDelta"])
    win_delta_text, win_delta_class = _format_rate_delta(entry["winRateDelta"])
    return RolesRankingRowItem(
        position=position,
        rank_class=_rank_class(position),
        portrait=portrait,
        initial=name[0] if name else "?",
        name=name,
        faction_name=faction_name,
        faction_dot_color=faction_dot_color,
        faction_text_color=faction_text_color,
        position_name=position_name,
        has_meta_tag=has_meta_tag,
        appearance_rate_text=f"{entry['appearanceRate'] * 100:.1f}%",
        appearance_delta_text=app_delta_text,
        appearance_delta_class=app_delta_class,
        win_rate_text=f"{entry['winRate'] * 100:.1f}%",
        win_delta_text=win_delta_text,
        win_delta_class=win_delta_class,
        games_text=f"{entry['games']:,}",
        wins_text=f"{entry['wins']:,}",
        players_text=f"{entry['players']:,}",
    )


def _build_roles_ranking_context(
    board: DakanuRolesRankingBoard,
    role_names: Mapping[int, str],
    role_images: Mapping[int, str],
    *,
    sort_by: str = "appearanceRate",
) -> RolesRankingTemplateContext:
    if sort_by not in {"appearanceRate", "winRate"}:
        raise ValueError(f"不支持的排序字段：{sort_by}")
    sorted_entries = _sort_entries(board["entries"], sort_by)
    rows = tuple(
        _build_row_item(idx, entry, role_names, role_images) for idx, entry in enumerate(sorted_entries, start=1)
    )
    title = "超弦体胜率排行" if sort_by == "winRate" else "超弦体登场率排行"
    scope_label = "仅排位" if board["rankedOnly"] else "全部模式"
    scope_class = "scope-ranked" if board["rankedOnly"] else "scope-all"
    return RolesRankingTemplateContext(
        title=title,
        scope_label=scope_label,
        scope_class=scope_class,
        covered_matches_text=f"{board['coveredMatches']:,} 场",
        day_text=board["day"],
        sort_by=sort_by,
        has_entries=bool(rows),
        rows=rows,
    )


def render_roles_ranking_html(
    board: DakanuRolesRankingBoard,
    role_names: Mapping[int, str],
    role_images: Mapping[int, str],
    *,
    sort_by: str = "appearanceRate",
) -> str:
    """生成超弦体排行榜完整 HTML 文档。"""
    context = _build_roles_ranking_context(
        board,
        role_names,
        role_images,
        sort_by=sort_by,
    )
    return render_template("roles_ranking_card.html", context)


async def render_roles_ranking_card(
    board: DakanuRolesRankingBoard,
    role_names: Mapping[int, str],
    role_images: Mapping[int, str],
    *,
    sort_by: str = "appearanceRate",
) -> bytes:
    """把超弦体排行榜渲染成 PNG 卡片。"""
    context = _build_roles_ranking_context(
        board,
        role_names,
        role_images,
        sort_by=sort_by,
    )
    return await render_card(
        "roles_ranking_card.html",
        context,
        width=CARD_WIDTH,
        default_font_size=14,
    )
