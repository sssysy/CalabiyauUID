"""历史战绩单列卡片。"""

from datetime import datetime
from dataclasses import dataclass
from collections.abc import Mapping

from ..render import CARD_WIDTH, CardTemplateContext, render_card, render_template
from ....helper.maps import MapInfo, resolve_map
from ....helper.recent_matches import MatchView
from ....api.dakanu.models.match import DakanuMatch, DakanuMatchPlayer
from ....api.dakanu.models.player import DakanuProfile


@dataclass(frozen=True)
class MatchCardAssets:
    player_avatar: str
    avatar_images: Mapping[int, str]
    role_images: Mapping[int, str]
    map_images: Mapping[str, str]
    clan_name: str


@dataclass(frozen=True)
class RosterPlayerItem:
    avatar: str
    initial: str
    nickname: str
    is_target: bool


@dataclass(frozen=True)
class RosterTeamItem:
    players: tuple[RosterPlayerItem, ...]


@dataclass(frozen=True)
class MatchCardItem:
    result_class: str
    result_label: str
    map_asset: str
    map_name: str
    mode_label: str
    played_at: str
    duration: str
    role_asset: str
    badge_text: str
    badge_tone: str
    kills: int
    deaths: int
    assists: int
    kda_ratio: str
    participation: str
    my_score: str
    opponent_score: str | None
    delta_text: str
    delta_class: str
    teams: tuple[RosterTeamItem, ...]
    room_id: str


@dataclass(frozen=True)
class MatchesTemplateContext(CardTemplateContext):
    player_avatar: str = ""
    player_initial: str = "?"
    nickname: str = ""
    uid: str = ""
    level: int = 0
    season: str = ""
    clan_name: str = ""
    match_count: int = 0
    matches: tuple[MatchCardItem, ...] = ()


def _date_text(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def _duration_text(seconds: int | None) -> str:
    if seconds is None or seconds <= 0:
        return "—"
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
        return match.kills or 0, match.deaths or 0, match.assists or 0
    return target.kills, target.deaths, target.assists


def _badge(match: DakanuMatch) -> tuple[str, str]:
    if match.mvp:
        return "MVP", "mvp"
    if match.svp:
        return "SVP", "svp"
    if match.result == "win" and match.myRanking == 1:
        return "MVP", "mvp"
    if match.result == "lose" and match.myRanking == 2:
        return "SVP", "svp"
    return "", ""


def _map_asset(assets: MatchCardAssets, map_info: MapInfo | None) -> str:
    if map_info is None:
        return ""
    if map_info.slug in assets.map_images:
        return assets.map_images[map_info.slug]
    return ""


def _role_asset(assets: MatchCardAssets, role_id: int | None) -> str:
    if role_id is not None and role_id in assets.role_images:
        return assets.role_images[role_id]
    return ""


def _avatar_asset(assets: MatchCardAssets, avatar_id: int) -> str:
    if avatar_id in assets.avatar_images:
        return assets.avatar_images[avatar_id]
    return ""


def _score_parts(match: DakanuMatch) -> tuple[str, str | None, str, str]:
    my_score = "—" if match.myScore is None else str(match.myScore)
    opponent_score = str(match.opponentScore) if match.opponentScore is not None else None
    delta_text = ""
    delta_class = ""
    if match.divisionScoreDelta is not None:
        delta = match.divisionScoreDelta
        delta_class = "is-up" if delta >= 0 else "is-down"
        delta_text = f"+{delta}" if delta >= 0 else str(delta)
    return my_score, opponent_score, delta_text, delta_class


def _build_roster_player(player: DakanuMatchPlayer, avatar: str, is_target: bool) -> RosterPlayerItem:
    return RosterPlayerItem(
        avatar=avatar,
        initial=player.nickname[:1] or "?",
        nickname=player.nickname,
        is_target=is_target,
    )


def _build_roster_teams(view: MatchView, assets: MatchCardAssets) -> tuple[RosterTeamItem, ...]:
    if not view.teams:
        return ()
    target_player_id = view.target_player.playerId if view.target_player is not None else ""
    teams: list[RosterTeamItem] = []
    for team in view.teams[:2]:
        players = tuple(
            _build_roster_player(
                player,
                _avatar_asset(assets, player.avatarId),
                player.isTarget or player.playerId == target_player_id,
            )
            for player in team.players
        )
        teams.append(RosterTeamItem(players=players))
    return tuple(teams)


def build_match_card_item(view: MatchView, assets: MatchCardAssets) -> MatchCardItem:
    match = view.match
    result_label, result_class = _result(match.result)
    role_asset = _role_asset(assets, match.roleId)
    map_info = resolve_map(match.mapId)
    map_asset = _map_asset(assets, map_info)
    map_name = map_info.name if map_info is not None else "地图未知"
    kills, deaths, assists = _match_stats(view)
    kda_ratio = (kills + assists) / deaths if deaths > 0 else float(kills + assists)
    team_kills = view.target_team_kills if view.target_team_kills is not None else match.teamKills
    participation = ""
    if team_kills is not None and team_kills > 0:
        ratio = round((kills + assists) / team_kills * 100)
        participation = f"击杀参与率 {ratio}%"
    badge_text, badge_tone = _badge(match)
    my_score, opponent_score, delta_text, delta_class = _score_parts(match)
    return MatchCardItem(
        result_class=result_class,
        result_label=result_label,
        map_asset=map_asset,
        map_name=map_name,
        mode_label=match.modeLabel,
        played_at=_date_text(match.playedAt),
        duration=_duration_text(match.durationSeconds),
        role_asset=role_asset,
        badge_text=badge_text,
        badge_tone=badge_tone,
        kills=kills,
        deaths=deaths,
        assists=assists,
        kda_ratio=f"{kda_ratio:.2f}",
        participation=participation,
        my_score=my_score,
        opponent_score=opponent_score,
        delta_text=delta_text,
        delta_class=delta_class,
        teams=_build_roster_teams(view, assets),
        room_id=match.roomId,
    )


def _build_matches_context(
    profile: DakanuProfile,
    views: list[MatchView],
    assets: MatchCardAssets,
) -> MatchesTemplateContext:
    player = profile.player
    return MatchesTemplateContext(
        player_avatar=assets.player_avatar,
        player_initial=player.nickname[:1] or "?",
        nickname=player.nickname,
        uid=player.id,
        level=player.level,
        season=profile.meta.currentSeason,
        clan_name=assets.clan_name,
        match_count=len(views),
        matches=tuple(build_match_card_item(view, assets) for view in views),
    )


def render_matches_html(profile: DakanuProfile, views: list[MatchView], assets: MatchCardAssets) -> str:
    """生成历史战绩完整 HTML 文档。"""
    return render_template("matches_card.html", _build_matches_context(profile, views, assets))


async def render_matches_card(profile: DakanuProfile, views: list[MatchView], assets: MatchCardAssets) -> bytes:
    """把历史战绩渲染成 PNG 卡片。"""
    return await render_card(
        "matches_card.html",
        _build_matches_context(profile, views, assets),
        width=CARD_WIDTH,
        default_font_size=14,
    )
