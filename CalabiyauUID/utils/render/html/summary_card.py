"""战绩总览静态卡片。"""

import html
from dataclasses import dataclass

from gsuid_core.utils.html_render import render_html_to_bytes

from ...api.dakanu import DakanuMode, DakanuRole, DakanuMatch, DakanuLeisure, DakanuProfile, DakanuSummary

_CARD_WIDTH = 760
_TREND_POINTS = 12

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


def _tier(segment: int) -> tuple[str, str, str]:
    for name, start, end, divisions, color, tier_index in _TIERS:
        if start <= segment <= end:
            division = divisions[segment - start] if divisions else ""
            label = f"{name} {division}" if division else name
            return label, color, str(tier_index)
    return "未定级", "#8d99ad", ""


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
    names = ("青铜", "白银", "黄金", "铂金", "翡翠", "钻石", "大师", "王者", "传说")
    if segment < 1 or segment > 41:
        return "", ""
    tier_index = min(8, (segment - 1) // 5)
    return names[tier_index], "#8f98a8"


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _num(value: float, digits: int = 0) -> str:
    if digits == 0:
        return f"{value:,.0f}"
    return f"{value:,.{digits}f}"


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


def _stat(label: str, value: str, tone: str = "") -> str:
    tone_class = f" is-{tone}" if tone else ""
    return (
        f'<div class="stat"><span class="stat-label">{_escape(label)}</span>'
        f'<span class="stat-value{tone_class}">{_escape(value)}</span></div>'
    )


def _trend_matches(profile: DakanuProfile) -> list[DakanuMatch]:
    ranked = [
        match for match in profile["historyMatches"] if "RANK" in match["mode"] and match["divisionScore"] is not None
    ]
    return list(reversed(ranked))[-_TREND_POINTS:]


def _trend_svg(matches: list[DakanuMatch]) -> str:
    if len(matches) < 2:
        return '<div class="trend-empty">排位对局不足，暂时无法绘制趋势</div>'
    scores = [match["divisionScore"] for match in matches if match["divisionScore"] is not None]
    if len(scores) < 2:
        return '<div class="trend-empty">排位对局不足，暂时无法绘制趋势</div>'
    low, high = min(scores), max(scores)
    span = max(1, high - low)
    points: list[str] = []
    dots: list[str] = []
    for index, score in enumerate(scores):
        x = 12 + index * (336 / (len(scores) - 1))
        y = 128 - ((score - low) / span) * 92
        points.append(f"{x:.1f},{y:.1f}")
        dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#f47b20" stroke="#fff" stroke-width="1.5"/>')
    line = " ".join(points)
    area = f"12,142 {line} 348,142"
    return (
        '<svg class="trend-svg" viewBox="0 0 360 150" width="360" height="150">'
        '<defs><linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="#f47b20" stop-opacity=".28"/>'
        '<stop offset="100%" stop-color="#f47b20" stop-opacity=".02"/>'
        "</linearGradient></defs>"
        f'<polygon points="{area}" fill="url(#trend-fill)"/>'
        f'<polyline points="{line}" fill="none" stroke="#f47b20" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
        + "".join(dots)
        + "</svg>"
    )


def render_empty_summary_html(message: str) -> str:
    """没有本地战绩时显示的最小卡片，避免输出空图片。"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8">
<title>战绩总览</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:100%;min-height:1px;background:#eceff4;color:#172033;font-family:"MiSans","Microsoft YaHei",sans-serif;font-size:15px}}
.empty-card{{width:100%;padding:42px 32px;background:linear-gradient(135deg,#f8fafc 0%,#e8edf4 100%);text-align:center}}
.empty-title{{font-size:22px;font-weight:700;color:#263247}}
.empty-text{{margin-top:12px;font-size:15px;line-height:1.6;color:#7c8799;white-space:pre-wrap}}
</style></head>
<body><div class="empty-card"><div class="empty-title">还没有战绩数据</div><div class="empty-text">{_escape(message)}</div></div></body></html>"""


async def render_empty_summary_card(message: str) -> bytes:
    return await render_html_to_bytes(
        render_empty_summary_html(message),
        max_width=1520,
        dpi=192,
        root_max_width=_CARD_WIDTH,
        default_font_size=15,
        allow_refit=True,
        image_format="png",
        lang="zh",
    )


def _trend_block(profile: DakanuProfile) -> str:
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
    return (
        '<div class="trend-wrap">'
        f'<div class="trend-chart">{_trend_svg(matches)}</div>'
        '<div class="trend-side">'
        f'<span class="trend-kicker">最近 {len(matches)} 场排位</span>'
        f'<div class="trend-tier" style="color:{tier_color}">{_escape(tier_label)}</div>'
        f'<div class="trend-score">{rank["divisionScore"]} 分</div>'
        f'<div class="trend-net {net_class}">{net_text}</div>'
        f'<div class="trend-record">{wins} 胜 {losses} 负 {draws} 平</div>'
        "</div></div>"
    )


def _role_card(role: DakanuRole, image: str) -> str:
    image_tag = f'<img src="{_escape(image)}" alt="">' if image else ""
    return (
        '<div class="role-card">'
        f'<div class="role-img">{image_tag}</div>'
        f'<div class="role-name">{_escape(role["name"])}</div>'
        f'<div class="role-rate">{_pct(role["winRate"])}</div>'
        f'<div class="role-count">{role["count"]} 场</div>'
        f'<div class="role-kd">K/D {role["kd"]:.2f}</div>'
        "</div>"
    )


def _mode_block(mode: DakanuMode, index: int) -> str:
    return (
        f'<div class="mode-block{" is-first" if index == 0 else ""}">'
        f'<div class="mode-head"><span class="mode-name">{_escape(mode["label"])}</span><span>{mode["rounds"]} 场</span></div>'
        '<div class="mode-grid">'
        '<div class="mode-grid-row">'
        f"{_stat('胜率', _pct(mode['winRate']), 'blue')}"
        f'<div class="stat"><span class="stat-label">K/D</span><span class="stat-value is-blue">{mode["kd"]:.2f}</span></div>'
        f"{_stat('场均伤害', _num(mode['avgDamage']))}"
        "</div>"
        '<div class="mode-grid-row">'
        f'<div class="stat"><span class="stat-label">场均击杀</span><span class="stat-value">{mode["avgKill"]:.2f}</span></div>'
        f"{_stat('爆头率', _pct(mode['headshotRate']))}"
        f"{_stat('MVP 率', _pct(mode['mvpRate']), 'gold')}"
        "</div>"
        "</div></div>"
    )


def render_summary_html(profile: DakanuProfile, assets: SummaryAssets) -> str:
    player = profile["player"]
    rank = profile["rank"]
    summary: DakanuSummary = profile["summary"]
    tier_label, tier_color, _ = _tier(rank["segment"])
    top_label, top_color, _ = _tier(rank["topSegment"])
    season = _escape(profile["meta"]["currentSeason"])
    roles = profile["roles"][:5]
    modes = profile["modes"][:3]
    avatar = _escape(assets.avatar)
    tier_icon = _escape(assets.tier_icon)
    top_tier_icon = _escape(assets.top_tier_icon)
    baseplate = _escape(assets.baseplate)
    clan_name = _escape(assets.clan_name)
    privacy_label = {"open": "生涯公开", "hidden": "生涯隐藏", "unavailable": "不可查询"}.get(
        player["privacyStatus"], "隐私未知"
    )
    verify_label = "已认证" if player["accountVerified"] else "历史未校验"
    clan_badge = (
        f'<span class="badge is-clan">战队 {clan_name}</span>' if clan_name else '<span class="badge">无战队</span>'
    )
    if baseplate and assets.frame:
        baseplate_html = (
            f'<div class="baseplate-art"><img src="{baseplate}" alt=""></div>'
            f'<div class="baseplate-frame"><img src="{_escape(assets.frame)}" alt=""></div>'
        )
    elif baseplate:
        baseplate_html = f'<div class="baseplate-art is-full"><img src="{baseplate}" alt=""></div>'
    else:
        baseplate_html = '<div class="challenge-empty">暂无基板展示图</div>'

    leisure = assets.leisure
    if leisure is not None and "segment" in leisure:
        challenge_name, challenge_color = _challenge_label(leisure["segment"])
        challenge_score = leisure.get("score", 0)
        challenge_rate = leisure.get("winRate", 0.0)
        challenge_html = (
            '<div class="rank-card-body">'
            f'<div class="rank-card-icon"><img src="{_escape(assets.challenge_icon)}" alt=""></div>'
            f'<div><div class="rank-card-name" style="color:{challenge_color}">{_escape(challenge_name)}</div>'
            f'<div class="rank-card-sub">{challenge_score} 挑战分 · 胜率 {_pct(challenge_rate)}</div></div>'
            f'<div class="rank-card-right"><b>{leisure.get("star", 0)}</b><span>星级</span></div>'
            "</div>"
        )
    else:
        challenge_html = '<div class="challenge-empty">暂无挑战赛段位数据</div>'
    previous = "、".join(player["previousNames"][:2]) or "无"
    rank_pos = f"#{rank['rankPos']}" if rank["rankPos"] is not None else "未上榜"
    wins = summary["wins"]
    losses = summary["losses"]
    bar_width = max(0.0, min(100.0, summary["winRate"] * 100))

    role_images = assets.role_images
    roles_html = (
        "".join(
            _role_card(role, role_images[index] if index < len(role_images) else "") for index, role in enumerate(roles)
        )
        or '<div class="empty">暂无角色使用数据</div>'
    )
    modes_html = (
        "".join(_mode_block(mode, index) for index, mode in enumerate(modes)) or '<div class="empty">暂无模式统计</div>'
    )
    trend_html = _trend_block(profile)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8">
<title>战绩总览</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:100%;min-height:1px;background:#eceff4;color:#172033;font-family:"MiSans","Microsoft YaHei",sans-serif;font-size:15px}}
.card{{width:100%;padding:24px 24px 0;background:linear-gradient(135deg,#f8fafc 0%,#e8edf4 55%,#dfe7f2 100%)}}
.top{{display:flex;gap:18px;align-items:flex-start}}
.identity{{width:252px;flex:none;align-self:flex-start;display:flex;flex-direction:column;background:#fff;border:1px solid #dce3ec;border-radius:16px;overflow:hidden;box-shadow:0 8px 24px rgba(39,55,80,.08)}}
.identity-main{{display:flex;gap:14px;align-items:center;padding:18px 16px;border-bottom:1px solid #e4e9f0}}
.avatar{{width:76px;height:76px;flex:none;border-radius:50%;overflow:hidden;background:#eef2f7;border:2px solid #fff;box-shadow:0 0 0 2px #e2e8f1}}
.avatar img{{display:block;width:100%;height:100%;object-fit:cover}}
.name{{font-size:21px;font-weight:700;line-height:1.25;overflow-wrap:anywhere;max-height:53px;overflow:hidden}}
.uid{{margin-top:5px;color:#7c8799;font-size:13px;letter-spacing:.2px}}
.season{{display:inline-block;margin-top:8px;padding:3px 8px;border-radius:6px;background:#edf3ff;color:#356fd1;font-size:12px;font-weight:600}}
.badges{{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}}
.badge{{display:inline-flex;align-items:center;padding:3px 8px;border-radius:6px;background:#f1f4f8;color:#68758a;font-size:11px;line-height:1.3;white-space:nowrap}}
.badge.is-open{{background:#eaf7f0;color:#23865d}}
.badge.is-clan{{background:#fff3e8;color:#a76222}}
.mini-grid{{display:flex;flex-wrap:wrap;gap:1px;background:#e4e9f0}}
.mini{{width:calc(50% - 1px);padding:10px 14px;background:#fff;min-height:58px}}
.mini-label{{display:block;color:#818da0;font-size:12px;margin-bottom:4px}}
.mini-value{{font-size:16px;font-weight:650;color:#263247;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}}
.rank-box{{padding:15px 16px 17px}}
.rank-head{{display:flex;align-items:center;justify-content:space-between;color:#7b8799;font-size:12px;margin-bottom:10px}}
.rank-line{{display:flex;align-items:center;gap:13px}}
.rank-icon{{width:68px;height:68px;flex:none;border-radius:50%;background:#f2f4f8;overflow:hidden}}
.rank-icon img{{display:block;width:100%;height:100%;object-fit:contain}}
.rank-name{{font-size:20px;font-weight:700;color:{tier_color};line-height:1.2}}
.rank-score{{margin-top:5px;font-size:13px;color:#667387}}
.rank-pos{{margin-left:auto;text-align:right}}
.rank-pos b{{display:block;font-size:28px;color:{tier_color};line-height:1}}
.rank-pos span{{display:block;margin-top:6px;font-size:11px;color:#8b96a8}}
.rank-foot{{display:flex;justify-content:space-between;margin-top:12px;padding-top:10px;border-top:1px solid #edf0f5;font-size:12px;color:#7d899b}}
.main{{flex:1;min-width:0;display:flex;flex-direction:column;gap:14px}}
.panel{{background:#fff;border:1px solid #dce3ec;border-radius:16px;box-shadow:0 8px 24px rgba(39,55,80,.07);overflow:hidden}}
.panel-head{{display:flex;align-items:center;justify-content:space-between;padding:13px 17px;border-bottom:1px solid #edf0f5}}
.panel-title{{font-size:15px;font-weight:700;color:#263247}}
.panel-note{{font-size:12px;color:#8994a6}}
.summary-top{{display:flex;flex-direction:column;gap:12px;padding:16px 17px 14px}}
.summary-highlight{{display:flex;gap:12px;width:100%}}
.highlight-item{{flex:1;min-width:0;padding:11px 13px;border-radius:10px;background:#fbfcfe;border:1px solid #e7ebf1}}
.highlight-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}}
.highlight-label{{font-size:12px;font-weight:700;color:#505e73}}
.highlight-sub{{font-size:11px;color:#8994a6}}
.highlight-val{{font-size:26px;font-weight:700;line-height:1.15;color:#263247}}
.highlight-val.is-blue{{color:#3778e8}}
.highlight-desc{{margin-top:6px;font-size:11px;color:#8994a6}}
.bar{{height:6px;margin-top:8px;border-radius:3px;background:#e8edf5;overflow:hidden}}
.bar-fill{{height:100%;border-radius:3px;background:linear-gradient(90deg,#4b8df2,#2c69d8)}}
.stats-table{{width:100%;display:flex;flex-direction:column;border:1px solid #e7ebf1;border-radius:10px;overflow:hidden}}
.stats-row{{display:flex;width:100%}}
.stat{{flex:1;min-width:0;min-height:56px;padding:8px 10px;background:#fff;border-right:1px solid #e7ebf1}}
.stat:last-child{{border-right:0}}
.stats-row:first-child .stat{{border-bottom:1px solid #e7ebf1}}
.stat-label{{display:block;color:#8490a2;font-size:11px;margin-bottom:3px;white-space:nowrap}}
.stat-value{{display:block;font-size:16px;font-weight:650;color:#273348;white-space:nowrap}}
.trend-wrap{{display:flex;align-items:center;gap:12px;padding:8px 14px 12px}}
.trend-chart{{width:330px;flex:none}}
.trend-svg{{display:block;width:330px;height:138px}}
.trend-side{{flex:1;min-width:0}}
.trend-kicker{{display:block;color:#8792a4;font-size:11px;margin-bottom:5px;white-space:nowrap}}
.trend-tier{{font-size:18px;font-weight:700;line-height:1.2;white-space:nowrap}}
.trend-score{{margin-top:5px;color:#596579;font-size:13px;white-space:nowrap}}
.trend-net{{margin-top:8px;font-size:26px;font-weight:700;line-height:1}}
.trend-net.is-up{{color:#ef5d5d}}
.trend-net.is-down{{color:#3f92e8}}
.trend-record{{margin-top:7px;color:#8994a6;font-size:11px;white-space:nowrap}}
.trend-empty{{padding:30px 17px;color:#98a2b2;text-align:center;font-size:13px}}
.rank-stack{{display:flex;flex-direction:column;gap:1px;background:#e7ebf1}}
.rank-card{{padding:12px 14px;background:#fff}}
.rank-card-head{{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px;color:#7b8799;font-size:11px;white-space:nowrap}}
.rank-card-body{{display:flex;align-items:center;gap:11px}}
.rank-card-icon{{width:52px;height:52px;flex:none;border-radius:50%;background:#f3f5f8;overflow:hidden}}
.rank-card-icon img{{display:block;width:100%;height:100%;object-fit:contain}}
.rank-card-name{{font-size:17px;font-weight:700;line-height:1.2;white-space:nowrap}}
.rank-card-sub{{margin-top:4px;color:#788497;font-size:11px;white-space:nowrap}}
.rank-card-right{{margin-left:auto;text-align:right}}
.rank-card-right b{{display:block;font-size:22px;line-height:1;color:#3c485b}}
.rank-card-right span{{display:block;margin-top:5px;color:#929cad;font-size:10px}}
.challenge-empty{{padding:18px 14px;color:#9aa4b4;font-size:12px;text-align:center;background:#fff}}
.baseplate{{padding:12px 14px;background:#fff;display:flex;flex-direction:column}}
.baseplate-label{{display:flex;justify-content:space-between;color:#7b8799;font-size:11px;margin-bottom:8px}}
.baseplate-stage{{position:relative;width:100%;height:490px;border-radius:8px;overflow:hidden;background:#f3f6fa}}
.baseplate-art{{position:absolute;left:10%;top:9%;right:10%;bottom:13%;border-radius:6px;overflow:hidden;background:#eef2f7}}
.baseplate-art.is-full{{left:0;top:0;right:0;bottom:0;border-radius:8px}}
.baseplate-art img{{display:block;width:100%;height:100%;object-fit:cover;object-position:center 26%}}
.baseplate-frame{{position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none}}
.baseplate-frame img{{display:block;width:100%;height:100%;object-fit:fill}}
.stat-value.is-blue{{color:#3778e8}}
.stat-value.is-gold{{color:#c39023}}
.complete-panel{{padding:0}}
.lower{{display:flex;flex-direction:column;gap:14px}}
.list{{padding:5px 0}}
.role-list{{display:flex;gap:8px;padding:12px 14px}}
.role-card{{flex:1;min-width:0;padding:7px 5px 8px;border:1px solid #e7ebf1;border-radius:10px;background:#fbfcfe;text-align:center}}
.role-img{{width:100%;height:84px;border-radius:7px;overflow:hidden;background:#edf2f8;margin-bottom:6px}}
.role-img img{{display:block;width:100%;height:100%;object-fit:cover;object-position:center top}}
.role-name{{font-size:12px;font-weight:700;color:#344156;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.role-rate{{margin-top:2px;font-size:14px;font-weight:700;color:#3778e8}}
.role-count{{margin-top:2px;font-size:10px;color:#7b8799;white-space:nowrap}}
.role-kd{{margin-top:1px;font-size:10px;color:#929cac;font-family:"Mono",Consolas,monospace;white-space:nowrap}}
.mode-block{{padding:9px 14px;border-bottom:1px solid #f2f4f8}}
.mode-block:last-child{{border-bottom:0}}
.mode-head{{display:flex;justify-content:space-between;color:#4a566b;font-size:13px;font-weight:600;margin-bottom:8px}}
.mode-name{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px}}
.mode-head span:last-child{{color:#97a1b1;font-weight:400;font-size:12px}}
.mode-grid{{display:flex;flex-direction:column;border:1px solid #edf0f5;border-radius:8px;overflow:hidden}}
.mode-grid-row{{display:flex;width:100%}}
.mode-grid .stat{{padding:6px 8px;width:33.3333%;min-height:48px;border-right:1px solid #edf0f5;border-bottom:1px solid #edf0f5}}
.mode-grid-row:last-child .stat{{border-bottom:0}}
.mode-grid .stat:nth-child(3){{border-right:0}}
.mode-grid .stat-label{{font-size:10px}}
.mode-grid .stat-value{{font-size:14px}}
.empty{{padding:22px 17px;color:#98a2b2;text-align:center;font-size:13px}}
.footer{{text-align:center;padding:8px 2px 6px;color:#929cac;font-size:11px}}
</style></head>
<body><div class="card">
<div class="top">
  <div class="identity">
    <div class="identity-main">
      <div class="avatar"><img src="{avatar}" alt=""></div>
      <div style="flex:1;min-width:0"><div class="name">{_escape(player["nickname"])}</div><div class="uid">UID {_escape(player["id"])}</div><span class="season">{season}</span><div class="badges"><span class="badge is-open">{_escape(privacy_label)}</span><span class="badge">{_escape(verify_label)}</span>{clan_badge}</div></div>
    </div>
    <div class="mini-grid">
      <div class="mini"><span class="mini-label">等级</span><span class="mini-value">{player["level"]}</span></div>
      <div class="mini"><span class="mini-label">赞誉</span><span class="mini-value">{player["laud"]}</span></div>
      <div class="mini"><span class="mini-label">曾用名</span><span class="mini-value">{_escape(previous)}</span></div>
      <div class="mini"><span class="mini-label">获赞</span><span class="mini-value">{rank["likeCount"]}</span></div>
    </div>
    <div class="rank-stack">
      <div class="rank-card">
        <div class="rank-card-head"><span>排位赛 · 当前段位</span><span>{season}</span></div>
        <div class="rank-card-body">
          <div class="rank-card-icon"><img src="{tier_icon}" alt=""></div>
          <div><div class="rank-card-name" style="color:{tier_color}">{_escape(tier_label)}</div><div class="rank-card-sub">{rank["divisionScore"]} 段位分</div></div>
          <div class="rank-card-right"><b>{_escape(rank_pos)}</b><span>段位排名</span></div>
        </div>
      </div>
      <div class="rank-card">
        <div class="rank-card-head"><span>排位赛 · 历史最高</span><span>赛季 S{rank["historicalSegmentSeason"]}</span></div>
        <div class="rank-card-body">
          <div class="rank-card-icon"><img src="{top_tier_icon}" alt=""></div>
          <div><div class="rank-card-name" style="color:{top_color}">{_escape(top_label)}</div><div class="rank-card-sub">{rank["topDivisionScore"]} 历史段位分</div></div>
          <div class="rank-card-right"><b>{rank["historicalSegmentPos"] if rank["historicalSegmentPos"] is not None else "—"}</b><span>历史排名</span></div>
        </div>
      </div>
      <div class="rank-card">
        <div class="rank-card-head"><span>挑战赛 · 段位</span><span>{season}</span></div>
        {challenge_html}
      </div>
      <div class="baseplate">
        <div class="baseplate-label"><span>基板</span><span>玩家展示图</span></div>
        <div class="baseplate-stage">{baseplate_html}</div>
      </div>
    </div>
  </div>
  <div class="main">
    <div class="panel">
      <div class="panel-head"><span class="panel-title">生涯总览</span><span class="panel-note">{summary["rounds"]} 场对局</span></div>
      <div class="summary-top">
        <div class="summary-highlight">
          <div class="highlight-item">
            <div class="highlight-head">
              <span class="highlight-label">胜率</span>
              <span class="highlight-sub">{wins} 胜 / {losses} 负</span>
            </div>
            <div class="highlight-val is-blue">{_pct(summary["winRate"])}</div>
            <div class="bar"><div class="bar-fill" style="width:{bar_width:.1f}%"></div></div>
          </div>
          <div class="highlight-item">
            <div class="highlight-head">
              <span class="highlight-label">K/D · KDA</span>
              <span class="highlight-sub">{summary["kills"]} / {summary["deaths"]} / {summary["assists"]}</span>
            </div>
            <div class="highlight-val">{summary["kd"]:.2f} <small style="font-size:15px;color:#788497;font-weight:400">/ {summary["kda"]:.2f}</small></div>
            <div class="highlight-desc">总击杀 / 死亡 / 助攻</div>
          </div>
        </div>
        <div class="stats-table">
          <div class="stats-row">
            <div class="stat"><span class="stat-label">场均伤害</span><span class="stat-value">{_num(summary["avgDamage"])}</span></div>
            <div class="stat"><span class="stat-label">回合均伤</span><span class="stat-value">{summary["roundAveDamage"]:.1f}</span></div>
            <div class="stat"><span class="stat-label">场均击杀</span><span class="stat-value">{summary["avgKill"]:.2f}</span></div>
            <div class="stat"><span class="stat-label">场均死亡</span><span class="stat-value">{summary["avgDeath"]:.2f}</span></div>
          </div>
          <div class="stats-row">
            <div class="stat"><span class="stat-label">场均助攻</span><span class="stat-value">{summary["avgAssist"]:.2f}</span></div>
            <div class="stat"><span class="stat-label">爆头率</span><span class="stat-value">{_pct(summary["headshotRate"])}</span></div>
            <div class="stat"><span class="stat-label">MVP 率</span><span class="stat-value is-gold">{_pct(summary["mvpRate"])}</span></div>
            <div class="stat"><span class="stat-label">MVP 次数</span><span class="stat-value is-gold">{summary["mvpCount"]}</span></div>
          </div>
        </div>
      </div>
    </div>
    <div class="panel"><div class="panel-head"><span class="panel-title">排位分趋势</span><span class="panel-note">最近 12 场排位</span></div>{trend_html}</div>
    <div class="lower">
      <div class="panel"><div class="panel-head"><span class="panel-title">角色使用</span><span class="panel-note">按场次</span></div><div class="role-list">{roles_html}</div></div>
      <div class="panel"><div class="panel-head"><span class="panel-title">模式统计</span><span class="panel-note">当前赛季</span></div>{modes_html}</div>
    </div>
  </div>
</div>
<div class="footer">Create by GsCore &amp; Power by CalabiyauUID &amp; Data by 白泉幽奈</div>
</div></body></html>"""


async def render_summary_card(profile: DakanuProfile, assets: SummaryAssets) -> bytes:
    """把总览数据渲染成 PNG 卡片。"""
    return await render_html_to_bytes(
        render_summary_html(profile, assets),
        max_width=1520,
        dpi=192,
        root_max_width=_CARD_WIDTH,
        default_font_size=15,
        allow_refit=True,
        image_format="png",
        lang="zh",
    )
