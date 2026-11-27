"""最近对局详情装配与展示数据。"""

import asyncio
from dataclasses import dataclass

from gsuid_core.logger import logger

from .match_cache import get_match_detail
from ..api.dakanu.client import DakanuError
from ..api.dakanu.models.match import DakanuMatch, DakanuMatchDetail, DakanuMatchPlayer

_DETAIL_CONCURRENCY = 2


@dataclass(frozen=True)
class MatchTeamView:
    team_id: str
    label: str
    outcome: str
    players: tuple[DakanuMatchPlayer, ...]


@dataclass(frozen=True)
class MatchView:
    match: DakanuMatch
    teams: tuple[MatchTeamView, ...]
    detail_available: bool
    target_player: DakanuMatchPlayer | None
    target_team_kills: int | None


def _player_matches_target(player: DakanuMatchPlayer, player_id: str) -> bool:
    return player.playerId == player_id or player.isTarget


def _team_outcome(match: DakanuMatch, team_id: str, target_team_id: str) -> str:
    if not target_team_id or match.result == "unknown":
        return "unknown"
    if team_id == target_team_id:
        return match.result
    if match.result == "win":
        return "lose"
    if match.result == "lose":
        return "win"
    return match.result


def build_match_view(match: DakanuMatch, detail: DakanuMatchDetail | None, player_id: str) -> MatchView:
    if detail is None:
        return MatchView(
            match=match,
            teams=(),
            detail_available=False,
            target_player=None,
            target_team_kills=None,
        )
    teams_raw = detail.teams
    target_team_id = ""
    target_player: DakanuMatchPlayer | None = None
    for team in teams_raw:
        for player in team.players:
            if _player_matches_target(player, player_id):
                target_team_id = team.id
                target_player = player
                break
        if target_team_id:
            break
    teams: list[MatchTeamView] = []
    for team in teams_raw:
        team_id = team.id
        teams.append(
            MatchTeamView(
                team_id=team_id,
                label=team.label,
                outcome=_team_outcome(match, team_id, target_team_id),
                players=tuple(team.players),
            )
        )
    target_team_kills: int | None = None
    if target_team_id:
        for team in teams_raw:
            if team.id == target_team_id:
                target_team_kills = sum(player.kills for player in team.players)
                break
    return MatchView(
        match=match,
        teams=tuple(teams),
        detail_available=bool(detail.teams),
        target_player=target_player,
        target_team_kills=target_team_kills,
    )


async def load_recent_match_views(
    player_id: str,
    matches: list[DakanuMatch],
    limit: int = 8,
) -> list[MatchView]:
    selected = matches[:limit]
    semaphore = asyncio.Semaphore(_DETAIL_CONCURRENCY)

    async def load_one(match: DakanuMatch) -> DakanuMatchDetail | None:
        async with semaphore:
            try:
                return await get_match_detail(player_id, match.roomId, match_mode=match.mode)
            except DakanuError as exc:
                logger.warning(f"[卡拉彼丘·历史战绩] 读取对局 {match.roomId} 详情失败：{exc}")
                return None

    details = await asyncio.gather(*(load_one(match) for match in selected))
    return [build_match_view(match, details[index], player_id) for index, match in enumerate(selected)]
