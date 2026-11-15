"""排位段位榜 HTML 卡片。"""

import html
from dataclasses import dataclass
from collections.abc import Mapping

from gsuid_core.utils.html_render import render_html_to_bytes

from ...api.dakanu import DakanuRankingEntry, DakanuRankingFloor, DakanuRankingsBoard
from .summary_card import tier_display

_CARD_WIDTH = 1000


@dataclass(frozen=True)
class RankingCardAssets:
    avatar_images: Mapping[int, str]
    role_images: Mapping[int, str]
    tier_images: Mapping[int, str]


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _lookup_image(images: Mapping[int, str], key: int) -> str:
    return images[key] if key in images else ""


def _avatar_html(entry: DakanuRankingEntry, assets: RankingCardAssets, *, fallback_class: str) -> str:
    uri = _lookup_image(assets.avatar_images, entry["avatarId"])
    if uri:
        return f'<img src="{_escape(uri)}" alt="">'
    initial = entry["nickname"][0] if entry["nickname"] else "?"
    return f'<span class="{fallback_class}">{_escape(initial)}</span>'


def _roles_html(roles: list[int], assets: RankingCardAssets, *, empty_html: str) -> str:
    chips: list[str] = []
    for role_id in roles[:3]:
        uri = _lookup_image(assets.role_images, role_id)
        if uri:
            chips.append(f'<span class="role-chip"><img src="{_escape(uri)}" alt=""></span>')
    return "".join(chips) if chips else empty_html


def _delta_html(score_delta: int | None) -> str:
    if score_delta is None:
        return '<span class="delta delta--flat">—</span>'
    if score_delta > 0:
        return f'<span class="delta delta--up">▲ {score_delta:,}</span>'
    if score_delta < 0:
        return f'<span class="delta delta--down">▼ {abs(score_delta):,}</span>'
    return '<span class="delta delta--flat">0</span>'


def _floor_pill_html(floor: DakanuRankingFloor | None) -> str:
    if floor is None:
        return ""
    score = floor["current"]["score"]
    delta = floor["yesterdayDelta"]
    delta_html = ""
    if delta is not None:
        if delta > 0:
            delta_html = f'<span class="pill-delta pill-delta--up">↑ {delta:,}</span>'
        elif delta < 0:
            delta_html = f'<span class="pill-delta pill-delta--down">↓ {abs(delta):,}</span>'
        else:
            delta_html = '<span class="pill-delta pill-delta--flat">0</span>'
    return f'<div class="head-pill"><span>当前奇点底分</span><strong>{score:,}</strong>{delta_html}</div>'


def _season_pill_html(season_label: str) -> str:
    if not season_label:
        return ""
    return (
        f'<div class="head-pill"><span>当前赛季</span><strong class="season-val">{_escape(season_label)}</strong></div>'
    )


def _podium_order(top_entries: list[DakanuRankingEntry]) -> list[DakanuRankingEntry]:
    if len(top_entries) >= 3:
        return [top_entries[1], top_entries[0], top_entries[2]]
    return list(top_entries)


def _podium_card_html(entry: DakanuRankingEntry, assets: RankingCardAssets) -> str:
    position = entry["position"]
    rank_class = f"podium-pos-{position}" if position in {1, 2, 3} else "podium-pos-other"
    card_class = " is-first" if position == 1 else ""
    tier_label, tier_color, tier_idx = tier_display(entry["segment"])
    tier_uri = _lookup_image(assets.tier_images, tier_idx) if tier_idx > 0 else ""
    tier_img = f'<img class="podium-tier-icon" src="{_escape(tier_uri)}" alt="">' if tier_uri else ""
    region = entry["region"].strip() if entry["region"] is not None else ""
    meta_text = f"等级 {entry['level']} · {region}" if region else f"等级 {entry['level']}"
    roles = _roles_html(entry["roles"], assets, empty_html="")
    roles_block = f'<div class="podium-roles">{roles}</div>' if roles else ""
    avatar = _avatar_html(entry, assets, fallback_class="podium-avatar-fallback")
    return (
        f'<div class="podium-card {rank_class}{card_class}">'
        f'<div class="podium-badge">{position}</div>'
        f'<div class="podium-avatar">{avatar}</div>'
        f'<div class="podium-name">{_escape(entry["nickname"])}</div>'
        f'<div class="podium-tier" style="color:{tier_color}">{tier_img}<span>{_escape(tier_label)}</span></div>'
        f'<div class="podium-meta">{_escape(meta_text)}</div>'
        f'<div class="podium-score">{entry["score"]:,}</div>'
        '<div class="podium-score-label">段位分</div>'
        f"{roles_block}"
        "</div>"
    )


def _row_html(entry: DakanuRankingEntry, assets: RankingCardAssets) -> str:
    tier_label, tier_color, tier_idx = tier_display(entry["segment"])
    tier_uri = _lookup_image(assets.tier_images, tier_idx) if tier_idx > 0 else ""
    tier_img = f'<img class="row-tier-icon" src="{_escape(tier_uri)}" alt="">' if tier_uri else ""
    region = entry["region"].strip() if entry["region"] is not None else ""
    region_text = region if region else "—"
    avatar = _avatar_html(entry, assets, fallback_class="row-avatar-fallback")
    roles = _roles_html(entry["roles"], assets, empty_html='<span class="delta--flat">—</span>')

    wins = max(0, entry["wins"])
    total_games = max(0, entry["totalGames"])
    losses = max(0, total_games - wins)
    win_rate = (wins / total_games * 100.0) if total_games > 0 else 0.0
    if wins == 0 and losses == 0:
        win_bar = '<div class="record-empty">暂无对局</div>'
    elif losses == 0:
        win_bar = f'<div class="record-win" style="width:100%">{wins}胜</div>'
    elif wins == 0:
        win_bar = f'<div class="record-loss" style="width:100%">{losses}负</div>'
    else:
        win_width = max(24.0, min(76.0, win_rate))
        loss_width = 100.0 - win_width
        win_bar = (
            f'<div class="record-win" style="width:{win_width:.1f}%">{wins}胜</div>'
            f'<div class="record-loss" style="width:{loss_width:.1f}%">{losses}负</div>'
        )

    return (
        '<div class="tr">'
        f'<div class="td col-pos">{entry["position"]}</div>'
        '<div class="td col-player">'
        f'<div class="row-avatar">{avatar}</div>'
        '<div class="player-text">'
        f'<div class="player-nick">{_escape(entry["nickname"])}</div>'
        f'<div class="player-uid">#{_escape(entry["playerId"])}</div>'
        "</div>"
        "</div>"
        f'<div class="td col-region">{_escape(region_text)}</div>'
        f'<div class="td col-tier" style="color:{tier_color}">{tier_img}<span>{_escape(tier_label)}</span></div>'
        f'<div class="td col-score">{entry["score"]:,}</div>'
        f'<div class="td col-delta">{_delta_html(entry["scoreDelta"])}</div>'
        f'<div class="td col-roles">{roles}</div>'
        '<div class="td col-record">'
        f'<div class="record-bar">{win_bar}</div>'
        f'<div class="record-rate">{win_rate:.0f}%</div>'
        "</div>"
        "</div>"
    )


def render_ranking_html(
    board: DakanuRankingsBoard,
    floor: DakanuRankingFloor | None,
    season_label: str,
    assets: RankingCardAssets,
) -> str:
    entries = board["entries"]
    title = board["rankType"]["label"] or "段位榜"
    podium_entries = _podium_order(entries[:3])
    podium_html = "".join(_podium_card_html(entry, assets) for entry in podium_entries)
    rows_html = "".join(_row_html(entry, assets) for entry in entries[3:])

    if entries:
        table_block = (
            f'<div class="podium">{podium_html}</div>'
            '<div class="table">'
            '<div class="tr head">'
            '<div class="td col-pos">排名</div>'
            '<div class="td col-player">玩家</div>'
            '<div class="td col-region">地区</div>'
            '<div class="td col-tier">段位</div>'
            '<div class="td col-score">段位分</div>'
            '<div class="td col-delta">较昨日</div>'
            '<div class="td col-roles">常用角色</div>'
            '<div class="td col-record col-record-head">胜率</div>'
            "</div>"
            f"{rows_html}"
            "</div>"
        )
    else:
        table_block = '<div class="empty-board">暂无榜单数据</div>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{_escape(title)}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:100%;min-height:1px;background:#eceff4;color:#172033;font-family:"MiSans","Microsoft YaHei",sans-serif;font-size:14px}}
.wrap{{width:100%;padding:20px;background:#eceff4}}
.card{{width:100%;background:#fff;border:1px solid rgba(22,26,33,.09);border-radius:12px;overflow:hidden;box-shadow:0 4px 16px rgba(22,26,33,.06)}}
.card-head{{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid rgba(22,26,33,.08);background:#fff}}
.card-title{{font-size:20px;font-weight:700;color:rgba(0,0,0,.88)}}
.head-actions{{display:flex;align-items:center;gap:10px}}
.head-pill{{display:flex;align-items:center;gap:7px;padding:6px 12px;border-radius:8px;background:#f3f5f8;border:1px solid rgba(22,26,33,.08);font-size:12px;color:rgba(0,0,0,.55)}}
.head-pill strong{{font-size:14px;font-weight:700;color:rgba(0,0,0,.88);font-family:"Mono",Consolas,monospace}}
.head-pill .season-val{{color:#d96b27}}
.pill-delta{{font-size:12px;font-weight:700;font-family:"Mono",Consolas,monospace}}
.pill-delta--up{{color:#17a34a}}
.pill-delta--down{{color:#e2453c}}
.pill-delta--flat{{color:rgba(0,0,0,.42)}}
.podium{{display:flex;align-items:flex-end;justify-content:center;gap:16px;padding:24px 24px 20px;border-bottom:1px solid rgba(22,26,33,.08);background:linear-gradient(180deg,#fafbfd 0%,#fff 100%)}}
.podium-card{{position:relative;flex:1;min-width:0;display:flex;flex-direction:column;align-items:center;padding:20px 14px 14px;border-radius:10px;border:1px solid rgba(22,26,33,.10);background:#f7f8fa;text-align:center}}
.podium-card.is-first{{padding:24px 16px 18px;border-color:rgba(212,160,36,.45);background:linear-gradient(180deg,#fffaf0 0%,#fffdf8 100%);box-shadow:0 6px 18px rgba(212,160,36,.10)}}
.podium-badge{{display:flex;align-items:center;justify-content:center;width:24px;height:24px;margin-bottom:-10px;z-index:2;border-radius:50%;font-size:12px;font-weight:700;color:#fff;font-family:"Mono",Consolas,monospace}}
.podium-pos-1 .podium-badge{{background:#d4a024}}
.podium-pos-2 .podium-badge{{background:#8c9ab0}}
.podium-pos-3 .podium-badge{{background:#c07a52}}
.podium-pos-other .podium-badge{{background:#6c7178}}
.podium-avatar{{display:flex;align-items:center;justify-content:center;width:62px;height:62px;border-radius:50%;overflow:hidden;border:2.5px solid #cbd5e1;background:#e5e7eb}}
.podium-card.is-first .podium-avatar{{width:72px;height:72px;border-color:#d4a024}}
.podium-pos-2 .podium-avatar{{border-color:#94a3b8}}
.podium-pos-3 .podium-avatar{{border-color:#c07a52}}
.podium-avatar img{{display:block;width:100%;height:100%;object-fit:cover}}
.podium-avatar-fallback{{font-size:22px;font-weight:700;color:#5b6c84}}
.podium-name{{width:100%;margin-top:10px;font-size:15px;font-weight:700;color:rgba(0,0,0,.88);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.podium-card.is-first .podium-name{{font-size:16px}}
.podium-tier{{display:flex;align-items:center;justify-content:center;gap:5px;margin-top:5px;font-size:13px;font-weight:600}}
.podium-tier-icon{{width:20px;height:20px;object-fit:contain}}
.podium-meta{{width:100%;margin-top:4px;font-size:11.5px;color:rgba(0,0,0,.48);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.podium-score{{margin-top:10px;font-size:26px;font-weight:700;line-height:1.1;color:#c96d28;font-family:"Mono",Consolas,monospace}}
.podium-card.is-first .podium-score{{font-size:30px}}
.podium-score-label{{margin-top:2px;font-size:11px;color:rgba(0,0,0,.44)}}
.podium-roles{{display:flex;align-items:center;justify-content:center;gap:6px;margin-top:10px}}
.role-chip{{display:flex;width:26px;height:26px;flex:none;border-radius:50%;overflow:hidden;border:1px solid rgba(22,26,33,.12);background:#eef2f7}}
.role-chip img{{display:block;width:100%;height:100%;object-fit:cover;object-position:center top}}
.table{{display:flex;flex-direction:column;width:100%}}
.tr{{display:flex;align-items:center;width:100%;padding:8px 16px;gap:10px;border-bottom:1px solid rgba(22,26,33,.09);font-size:13px}}
.tr.head{{background:#eef0f3;color:rgba(0,0,0,.48);font-size:11.5px;font-weight:600;padding:9px 16px}}
.tr:last-child{{border-bottom:none}}
.td{{min-width:0}}
.col-pos{{width:40px;flex:none;text-align:right;font-weight:700;color:rgba(0,0,0,.62);font-family:"Mono",Consolas,monospace}}
.col-player{{flex:1.5;display:flex;align-items:center;gap:10px}}
.row-avatar{{display:flex;align-items:center;justify-content:center;width:38px;height:38px;flex:none;border-radius:50%;overflow:hidden;border:1px solid rgba(22,26,33,.12);background:#e5e7eb}}
.row-avatar img{{display:block;width:100%;height:100%;object-fit:cover}}
.row-avatar-fallback{{font-size:14px;font-weight:700;color:#5b6c84}}
.player-text{{min-width:0;display:flex;flex-direction:column;gap:1px}}
.player-nick{{font-size:13.5px;font-weight:650;color:rgba(0,0,0,.86);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.player-uid{{font-size:11px;color:rgba(0,0,0,.42);font-family:"Mono",Consolas,monospace}}
.col-region{{width:98px;flex:none;font-size:12px;color:rgba(0,0,0,.60);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.col-tier{{width:94px;flex:none;display:flex;align-items:center;gap:6px;font-size:12.5px;font-weight:600}}
.row-tier-icon{{width:22px;height:22px;flex:none;object-fit:contain}}
.col-score{{width:72px;flex:none;text-align:right;font-weight:700;color:rgba(0,0,0,.86);font-family:"Mono",Consolas,monospace}}
.col-delta{{width:66px;flex:none;text-align:right;font-weight:700;font-family:"Mono",Consolas,monospace}}
.delta{{font-size:12px;font-weight:700}}
.delta--up{{color:#17a34a}}
.delta--down{{color:#e2453c}}
.delta--flat{{color:rgba(0,0,0,.38);font-weight:500}}
.col-roles{{width:96px;flex:none;display:flex;align-items:center;gap:5px}}
.col-record{{width:190px;flex:none;display:flex;align-items:center;justify-content:flex-end;gap:8px}}
.col-record-head{{justify-content:flex-start}}
.record-bar{{width:136px;height:22px;flex:none;display:flex;border-radius:4px;overflow:hidden;background:#eef0f3}}
.record-win{{background:#4b8ef0;color:#fff;font-size:11.5px;font-weight:700;display:flex;align-items:center;justify-content:center;white-space:nowrap;overflow:hidden}}
.record-loss{{background:#e2453c;color:#fff;font-size:11.5px;font-weight:700;display:flex;align-items:center;justify-content:center;white-space:nowrap;overflow:hidden}}
.record-empty{{width:100%;display:flex;align-items:center;justify-content:center;font-size:11px;color:rgba(0,0,0,.42)}}
.record-rate{{width:42px;flex:none;text-align:right;font-weight:650;color:rgba(0,0,0,.78);font-family:"Mono",Consolas,monospace}}
.empty-board{{padding:48px 20px;text-align:center;color:rgba(0,0,0,.48);font-size:14px}}
.footer{{text-align:center;padding-top:12px;font-size:11px;color:rgba(0,0,0,.42)}}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <div class="card-head">
      <div class="card-title">{_escape(title)}</div>
      <div class="head-actions">
        {_floor_pill_html(floor)}
        {_season_pill_html(season_label)}
      </div>
    </div>
    {table_block}
  </div>
  <div class="footer">Create by GsCore &amp; Power by sssysy/CalabiyauUID &amp; Data by 白泉幽奈</div>
</div>
</body>
</html>"""


async def render_ranking_card(
    board: DakanuRankingsBoard,
    floor: DakanuRankingFloor | None,
    season_label: str,
    assets: RankingCardAssets,
) -> bytes:
    """把排位排行榜渲染成 PNG 卡片。"""
    return await render_html_to_bytes(
        render_ranking_html(board, floor, season_label, assets),
        max_width=2000,
        dpi=192,
        root_max_width=_CARD_WIDTH,
        default_font_size=14,
        allow_refit=True,
        image_format="png",
        lang="zh",
    )
