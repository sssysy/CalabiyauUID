"""历史战绩单列卡片。"""

import html
from datetime import datetime
from dataclasses import dataclass
from collections.abc import Mapping

from gsuid_core.utils.html_render import render_html_to_bytes

from ...api.dakanu import DakanuMatch, DakanuProfile, DakanuMatchPlayer
from ...helper.maps import MapInfo, resolve_map
from ...helper.recent_matches import MatchView

_CARD_WIDTH = 760


@dataclass(frozen=True)
class MatchCardAssets:
    player_avatar: str
    avatar_images: Mapping[int, str]
    role_images: Mapping[int, str]
    map_images: Mapping[str, str]
    clan_name: str


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


def _date_text(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def _duration_text(seconds: int) -> str:
    minutes, remainder = divmod(max(0, seconds), 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours} 小时 {minutes} 分 {remainder} 秒"
    return f"{minutes} 分 {remainder} 秒"


def _result(result: str) -> tuple[str, str]:
    if result == "win":
        return "胜利", "win"
    if result == "lose":
        return "失败", "lose"
    if result == "draw":
        return "平局", "draw"
    return "未知", "unknown"


def _match_stats(view: MatchView) -> tuple[int, int, int]:
    target = view.target_player
    if target is None:
        match = view.match
        return match["kills"], match["deaths"], match["assists"]
    return target["kills"], target["deaths"], target["assists"]


def _badge(match: DakanuMatch) -> tuple[str, str]:
    if match["mvp"]:
        return "MVP", "mvp"
    if match["svp"]:
        return "SVP", "svp"
    if match["result"] == "win" and match["myRanking"] == 1:
        return "MVP", "mvp"
    if match["result"] == "lose" and match["myRanking"] == 2:
        return "SVP", "svp"
    return "", ""


def _map_asset(assets: MatchCardAssets, map_info: MapInfo | None) -> str:
    if map_info is None:
        return ""
    if map_info.slug in assets.map_images:
        return assets.map_images[map_info.slug]
    return ""


def _role_asset(assets: MatchCardAssets, role_id: int) -> str:
    if role_id in assets.role_images:
        return assets.role_images[role_id]
    return ""


def _avatar_asset(assets: MatchCardAssets, avatar_id: int) -> str:
    if avatar_id in assets.avatar_images:
        return assets.avatar_images[avatar_id]
    return ""


def _score_html(match: DakanuMatch) -> str:
    my_score = "—" if match["myScore"] is None else str(match["myScore"])
    if match["opponentScore"] is None:
        score = f'<span class="score-single">{_escape(my_score)}</span>'
    else:
        opponent_score = str(match["opponentScore"])
        score = (
            f'<span class="score-self">{_escape(my_score)}</span>'
            '<span class="score-sep">:</span>'
            f'<span class="score-op">{_escape(opponent_score)}</span>'
        )
    delta_html = ""
    if match["divisionScoreDelta"] is not None:
        delta = match["divisionScoreDelta"]
        delta_class = "is-up" if delta >= 0 else "is-down"
        delta_text = f"+{delta}" if delta >= 0 else str(delta)
        delta_html = f'<span class="delta {delta_class}">{_escape(delta_text)}</span>'
    return f'<div class="score-line">{score}</div><span class="score-label">得分</span>{delta_html}'


def _roster_player_html(player: DakanuMatchPlayer, avatar: str, is_target: bool) -> str:
    target_class = " is-target" if is_target else ""
    if avatar:
        avatar_html = f'<span class="mini-avatar"><img src="{_escape(avatar)}" alt=""></span>'
    else:
        initial = player["nickname"][:1] or "?"
        avatar_html = f'<span class="mini-avatar is-empty">{_escape(initial)}</span>'
    return (
        f'<div class="roster-player{target_class}">'
        f"{avatar_html}"
        f'<span class="roster-name">{_escape(player["nickname"])}</span>'
        "</div>"
    )


def _roster_html(view: MatchView, assets: MatchCardAssets) -> str:
    if not view.teams:
        return '<div class="roster is-empty">阵容详情暂不可用</div>'
    target_player_id = view.target_player["playerId"] if view.target_player is not None else ""
    teams_html: list[str] = []
    for team in view.teams[:2]:
        players = "".join(
            _roster_player_html(
                player,
                _avatar_asset(assets, player["avatarId"]),
                player["isTarget"] or player["playerId"] == target_player_id,
            )
            for player in team.players
        )
        teams_html.append(f'<div class="roster-team">{players}</div>')
    return f'<div class="roster">{"".join(teams_html)}</div>'


def _match_html(view: MatchView, assets: MatchCardAssets) -> str:
    match = view.match
    result_label, result_class = _result(match["result"])
    role_asset = _role_asset(assets, match["roleId"])
    map_info = resolve_map(match["mapId"])
    map_asset = _map_asset(assets, map_info)
    map_name = map_info.name if map_info is not None else "地图未知"
    kills, deaths, assists = _match_stats(view)
    kda_ratio = (kills + assists) / deaths if deaths > 0 else float(kills + assists)
    team_kills = view.target_team_kills if view.target_team_kills is not None else match["teamKills"]
    participation = ""
    if team_kills is not None and team_kills > 0:
        ratio = round((kills + assists) / team_kills * 100)
        participation = f'<span class="kda-extra">击杀参与率 {ratio}%</span>'
    badge_text, badge_tone = _badge(match)
    badge_html = f'<span class="badge badge-{badge_tone}">{badge_text}</span>' if badge_text else ""
    role_html = (
        f'<div class="role-art"><img src="{_escape(role_asset)}" alt=""></div>'
        if role_asset
        else '<div class="role-art role-empty"></div>'
    )
    map_art = (
        f'<div class="match-art" style="background-image:url(\'{_escape(map_asset)}\')"></div>' if map_asset else ""
    )
    match_veil = '<div class="match-veil"></div>' if map_asset else ""
    return f"""<article class="match match-{result_class}">
<div class="match-bar"></div>
<div class="match-main">
{map_art}
{match_veil}
<div class="match-content">
  <div class="match-info">
    <span class="mode">{_escape(match["modeLabel"])}</span>
    <span class="time">{_escape(_date_text(match["playedAt"]))}</span>
    <span class="result">{result_label}</span>
    <span class="duration">{_escape(_duration_text(match["durationSeconds"]))}</span>
  </div>
  <div class="kda-wrap">
    <div class="role-wrap">{role_html}{badge_html}</div>
    <div class="kda-body">
      <span class="kda-line"><b>{kills}</b><i>/</i><b class="death">{deaths}</b><i>/</i><b>{assists}</b></span>
      <span class="kda-ratio">{kda_ratio:.2f} : 1 KDA</span>
      {participation}
    </div>
  </div>
  <div class="score-box">{_score_html(match)}<span class="map-name">{_escape(map_name)}</span></div>
  {_roster_html(view, assets)}
</div>
<div class="match-footer"><span>对局编号：{_escape(match["roomId"])}</span></div>
</div>
</article>"""


def render_matches_html(profile: DakanuProfile, views: list[MatchView], assets: MatchCardAssets) -> str:
    player = profile["player"]
    clan_html = f'<span class="clan">{_escape(assets.clan_name)}</span>' if assets.clan_name else ""
    player_avatar = (
        f'<img src="{_escape(assets.player_avatar)}" alt="">'
        if assets.player_avatar
        else f'<span class="avatar-fallback">{_escape(player["nickname"][:1] or "?")}</span>'
    )
    match_html = "".join(_match_html(view, assets) for view in views)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8">
<title>历史战绩</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:100%;min-height:1px;background:#e9edf2;color:#172033;font-family:"MiSans","Microsoft YaHei",sans-serif;font-size:14px}}
.card{{width:100%;padding:24px;background:linear-gradient(145deg,#f8fafc 0%,#e9eef4 100%)}}
.header{{display:flex;align-items:center;gap:14px;padding:17px 20px;border:1px solid #dce3ec;border-radius:12px;background:#fff;box-shadow:0 5px 18px rgba(22,26,33,.07)}}
.avatar{{display:flex;width:66px;height:66px;flex:none;align-items:center;justify-content:center;border:3px solid #fff;border-radius:50%;overflow:hidden;background:#dce3eb;box-shadow:0 3px 10px rgba(0,0,0,.16)}}
.avatar img{{display:block;width:100%;height:100%;object-fit:cover}}
.avatar-fallback{{font-size:24px;font-weight:700;color:#5b6c84}}
.player-meta{{display:flex;flex:1;flex-direction:column;gap:4px;min-width:0}}
.player-name{{font-size:23px;font-weight:700;line-height:1.15;overflow-wrap:anywhere}}
.player-sub{{display:flex;align-items:center;gap:8px;color:#68758a;font-size:12px;flex-wrap:wrap}}
.clan{{padding:3px 8px;border-radius:999px;background:#e7edf4;color:#45607a;font-size:11px;font-weight:600}}
.title-block{{text-align:right;flex:none}}
.title{{font-size:20px;font-weight:700}}
.title-note{{margin-top:3px;color:#7c8799;font-size:11px}}
.section-head{{display:flex;align-items:center;justify-content:space-between;margin:18px 4px 9px}}
.section-title{{font-size:16px;font-weight:700}}
.matches{{display:flex;flex-direction:column;border:1px solid #dce3ec;border-radius:12px;overflow:hidden;background:#f7f8fa;box-shadow:0 5px 18px rgba(22,26,33,.06)}}
.match{{display:flex;border-bottom:1px solid #e2e7ee;background:#f7f8fa}}
.match:last-child{{border-bottom:none}}
.match-win .match-main{{background:#f3f7ff}}
.match-lose .match-main{{background:#fff5f4}}
.match-draw .match-main{{background:#fffaf0}}
.match-bar{{width:4px;flex:none;background:#4b8ef0}}
.match-lose .match-bar{{background:#e2453c}}
.match-draw .match-bar{{background:#b8862c}}
.match-unknown .match-bar{{background:#9aa5b5}}
.match-main{{position:relative;display:flex;flex:1;flex-direction:column;min-width:0;overflow:hidden}}
.match-art{{position:absolute;left:0;top:0;right:0;bottom:0;background-size:cover;background-position:center 30%;background-repeat:no-repeat}}
.match-veil{{position:absolute;left:0;top:0;right:0;bottom:0;background:rgba(255,255,255,.58)}}
.match-win .match-veil{{background:rgba(243,247,255,.56)}}
.match-lose .match-veil{{background:rgba(255,245,244,.56)}}
.match-draw .match-veil{{background:rgba(255,250,240,.56)}}
.match-content{{position:relative;display:flex;align-items:center;gap:10px;flex:1;min-width:0;padding:12px 14px 7px}}
.match-info{{display:flex;width:104px;flex:none;flex-direction:column;gap:2px;min-width:0}}
.mode{{overflow:hidden;font-size:12.5px;font-weight:700;text-overflow:ellipsis;white-space:nowrap}}
.time,.duration{{font-size:10.5px;color:#68758a}}
.result{{font-size:12.5px;font-weight:700;color:#2563eb}}
.match-lose .result{{color:#c62828}}
.match-draw .result{{color:#946200}}
.match-unknown .result{{color:#6f7c8f}}
.kda-wrap{{display:flex;width:172px;flex:none;align-items:center;gap:10px;min-width:0}}
.role-wrap{{position:relative;display:flex;width:52px;height:56px;flex:none;align-items:flex-end;justify-content:center}}
.role-art{{display:flex;width:50px;height:54px;overflow:hidden;border-radius:9px;background:#edf2f8}}
.role-art img{{display:block;width:100%;height:100%;object-fit:cover;object-position:center top}}
.role-empty{{width:44px;height:44px;border:1px dashed #b4bfce;border-radius:50%;background:transparent}}
.badge{{position:absolute;left:50%;bottom:-1px;padding:0 5px;transform:translateX(-50%);border-radius:4px;font-size:9px;font-weight:700;line-height:14px;white-space:nowrap;color:#fff;box-shadow:0 1px 4px rgba(0,0,0,.28)}}
.badge-mvp{{background:#b8862c}}
.badge-svp{{background:#4b8ef0}}
.kda-body{{display:flex;flex-direction:column;gap:1px;min-width:0}}
.kda-line{{font-size:17px;font-weight:700;line-height:1.15;white-space:nowrap}}
.kda-line i{{margin:0 3px;font-style:normal;color:#8a96a7}}
.kda-line .death{{color:#c62828}}
.kda-ratio,.kda-extra{{font-size:10.5px;color:#68758a;white-space:nowrap}}
.score-box{{display:flex;width:94px;flex:none;flex-direction:column;align-items:center;gap:2px;text-align:center}}
.score-line{{display:flex;align-items:baseline;justify-content:center;gap:4px;font-size:19px;font-weight:700;line-height:1.05}}
.score-single,.score-self{{color:#3b4a5f}}
.match-win .score-self{{color:#208a49}}
.match-lose .score-self{{color:#c62828}}
.score-op{{color:#3b4a5f}}
.score-sep{{color:#53657a;font-size:12px;font-weight:600}}
.score-label{{color:#3b4a5f;font-size:10px;font-weight:600}}
.delta{{font-size:10.5px;font-weight:700}}
.delta.is-up{{color:#168343}}
.delta.is-down{{color:#c62828}}
.map-name{{max-width:94px;overflow:hidden;color:#68758a;font-size:10.5px;text-overflow:ellipsis;white-space:nowrap}}
.roster{{display:flex;flex:1;gap:8px;min-width:0;padding-left:11px;border-left:1px solid #d8e0ea}}
.roster-team{{display:flex;flex:1;flex-direction:column;min-width:0}}
.roster-player{{display:flex;align-items:center;gap:4px;min-width:0;height:16px}}
.mini-avatar{{display:flex;width:14px;height:14px;flex:none;align-items:center;justify-content:center;overflow:hidden;border-radius:3px;background:#dce3eb;font-size:8px;font-weight:700;color:#53657a}}
.mini-avatar img{{display:block;width:100%;height:100%;object-fit:cover}}
.roster-name{{display:block;max-width:100px;overflow:hidden;font-size:9.5px;line-height:12px;text-overflow:ellipsis;white-space:nowrap;color:#68758a}}
.is-target .roster-name{{color:#18784a;font-weight:700}}
.roster.is-empty{{align-items:center;justify-content:center;color:#8a96a7;font-size:10.5px}}
.match-footer{{position:relative;padding:0 14px 8px;color:#8a96a7;font-size:9px}}
.match-footer span{{padding:2px 6px;border-radius:4px;background:rgba(255,255,255,.62);font-family:"Mono",monospace}}
.footer{{margin-top:14px;color:#7c8799;font-size:10px;text-align:center}}
</style></head>
<body><div class="card">
<div class="header">
  <span class="avatar">{player_avatar}</span>
  <div class="player-meta">
    <span class="player-name">{_escape(player["nickname"])}</span>
    <div class="player-sub"><span>UID {_escape(player["id"])}</span><span>Lv.{player["level"]}</span><span>{_escape(profile["meta"]["currentSeason"])}</span>{clan_html}</div>
  </div>
  <div class="title-block"><div class="title">历史战绩</div><div class="title-note">最近 {len(views)} 场 · 数据来自 Dakanu</div></div>
</div>
<div class="section-head"><span class="section-title">对局记录</span></div>
<div class="matches">{match_html}</div>
<div class="footer">Create by GsCore &amp; Power by sssysy/CalabiyauUID &amp; Data by 白泉幽奈</div>
</div></body></html>"""


async def render_matches_card(profile: DakanuProfile, views: list[MatchView], assets: MatchCardAssets) -> bytes:
    """把历史战绩渲染成 PNG 卡片。"""
    return await render_html_to_bytes(
        render_matches_html(profile, views, assets),
        max_width=1520,
        dpi=192,
        root_max_width=_CARD_WIDTH,
        default_font_size=14,
        allow_refit=True,
        image_format="png",
        lang="zh",
    )
