"""对局分析的局号解析、回放统计装配与卡片渲染编排。"""

import io
import base64
import asyncio
from pathlib import Path
from dataclasses import dataclass
from collections.abc import Callable

from PIL import Image

from gsuid_core.pool import to_thread
from gsuid_core.logger import logger

from ..utils.downloader import resolve_image
from ..utils.helper.assets import local_role_image, local_faction_image, read_image_data_uri
from ..utils.api.dakanu.assets import role_image_url
from ..utils.api.dakanu.client import DakanuError
from ..utils.helper.match_cache import get_match_detail, get_match_statistics
from ..utils.api.dakanu.models.match import DakanuMatchDetail, DakanuMatchPlayer, is_valid_room_id
from ..utils.api.dakanu.models.match_stats import (
    DakanuStatsTeam,
    DakanuStatsPlayer,
    DakanuStatsAccuracy,
    DakanuMatchStatistics,
    DakanuStatsRoundPlayer,
    DakanuStatsRoundResult,
)
from ..utils.render.html.renderer.match_analysis_card import (
    MatchAnalysisPlayerRow,
    MatchAnalysisRoundItem,
    MatchAnalysisStripItem,
    MatchAnalysisTeamSummary,
    MatchAnalysisRoundTeamCol,
    MatchAnalysisRoundPlayerRow,
    MatchAnalysisTemplateContext,
    render_match_analysis_card,
)

_OBSERVER_TEAM_IDS = {"254", "RoomCamp_CAMP_OB"}
_BLUE_COLOR = "#2563eb"
_RED_COLOR = "#dc2626"
_BLUE_RGB = (37, 99, 235)
_RED_RGB = (220, 38, 38)
_FACTION_WATERMARK_ALPHA = 68

_PHASE_LABELS: dict[str, str] = {
    "first_half": "上半场",
    "second_half": "下半场",
    "first_half_extra": "加时赛",
    "second_half_extra": "加时赛",
}

_MODE_LABELS: dict[str, str] = {
    "RoomMode_RANK_BOMB": "排位爆破",
    "RoomMode_MATCH_BOMB": "一般爆破",
    "RoomMode_CUSTOM_BOMB": "自定义爆破",
}


@dataclass(frozen=True)
class _ResolvedRound:
    index: int
    start_ms: int
    end_ms: int
    phase: str
    reason: str
    attack_team_id: str | None
    defense_team_id: str | None
    winner_team_id: str | None
    winner_side: str
    players: tuple[DakanuStatsRoundPlayer, ...]


@dataclass(frozen=True)
class _TeamSummaryBundle:
    summary: MatchAnalysisTeamSummary
    player_order: tuple[str, ...]


def parse_analysis_room_id(raw_text: str) -> str | None:
    """提取并校验对局 ID，非法时返回 None。"""
    cleaned = raw_text.strip()
    if not is_valid_room_id(cleaned):
        return None
    return cleaned


def _format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def _format_duration_ms(duration_ms: int) -> str:
    if duration_ms < 0:
        return "-"
    total_seconds = duration_ms // 1000
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"


async def _resolve_role_uri(role_id: int) -> str:
    cached = await read_image_data_uri(local_role_image(role_id))
    if cached:
        return cached
    path = await resolve_image(role_image_url(role_id), local_role_image(role_id))
    return await read_image_data_uri(path)


async def _load_role_uris(role_ids: set[int]) -> dict[int, str]:
    ordered = sorted(role_id for role_id in role_ids if role_id > 0)
    if not ordered:
        return {}
    uris = await asyncio.gather(*(_resolve_role_uri(role_id) for role_id in ordered))
    return {role_id: uri for role_id, uri in zip(ordered, uris, strict=True)}


def _load_tinted_faction_uri(path: Path | None, rgb: tuple[int, int, int]) -> str:
    if path is None or not path.is_file():
        return ""
    image = Image.open(path).convert("RGBA")
    alpha = image.getchannel("A")
    extrema = alpha.getextrema()
    max_alpha = float(extrema[1])
    if max_alpha <= 0:
        return ""
    scale = _FACTION_WATERMARK_ALPHA / max_alpha
    scaled_alpha = alpha.point(lambda val: min(255, int(val * scale)))
    tinted = Image.new("RGBA", image.size, (rgb[0], rgb[1], rgb[2], 0))
    tinted.putalpha(scaled_alpha)
    buffer = io.BytesIO()
    tinted.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _build_role_resolver(stats: DakanuMatchStatistics) -> Callable[[str, int], int | None]:
    timelines: dict[str, list[tuple[int, int, int | None]]] = {}
    for role_event in stats.role_timeline:
        if role_event.player_id not in timelines:
            timelines[role_event.player_id] = []
        timelines[role_event.player_id].append((role_event.at_ms, role_event.order, role_event.role_id))
    for entries in timelines.values():
        entries.sort(key=lambda entry: (entry[0], entry[1]))

    fallback_role: dict[str, int] = {
        player.player_id: player.role_id
        for player in stats.players
        if player.role_id is not None and player.role_id > 0
    }

    fight_times = [point.at_ms for point in stats.phase_timeline if point.phase == "fight"]
    round_anchors: dict[int, int] = {}
    for round_item in stats.rounds:
        anchor = next(
            (at_ms for at_ms in fight_times if round_item.start_ms <= at_ms < round_item.end_ms),
            None,
        )
        if anchor is None:
            anchor = next(
                (
                    event.at_ms
                    for event in stats.events
                    if event.event_type in ("PlayerDeath", "PlayerInjured")
                    and round_item.start_ms <= event.at_ms < round_item.end_ms
                ),
                None,
            )
        round_anchors[round_item.index] = anchor if anchor is not None else round_item.end_ms - 1

    def resolve_in_round(player_id: str, round_index: int) -> int | None:
        if round_index in round_anchors and player_id in timelines:
            anchor_ms = round_anchors[round_index]
            chosen: int | None = None
            for at_ms, _, role_id in timelines[player_id]:
                if at_ms <= anchor_ms:
                    if role_id is not None:
                        chosen = role_id
                else:
                    break
            if chosen is not None:
                return chosen
        if player_id in fallback_role:
            return fallback_role[player_id]
        return None

    return resolve_in_round


def _other_team_id(team_ids: tuple[str, str], team_id: str) -> str:
    return team_ids[1] if team_ids[0] == team_id else team_ids[0]


def _resolve_rounds(
    stats: DakanuMatchStatistics,
    active_teams: tuple[DakanuStatsTeam, DakanuStatsTeam],
    detail_team_side: dict[str, str],
) -> list[_ResolvedRound]:
    ordered_rounds = sorted(stats.rounds, key=lambda round_item: round_item.index)
    result_map: dict[int, DakanuStatsRoundResult] = {item.round_index: item for item in stats.round_results}
    team_ids = (active_teams[0].team_id, active_teams[1].team_id)
    player_team_map: dict[str, str] = {}
    for team in active_teams:
        for player_id in team.player_ids:
            player_team_map[player_id] = team.team_id

    sorted_events = sorted(stats.events, key=lambda event: event.at_ms)
    fight_ends = [point.at_ms for point in stats.phase_timeline if point.phase == "fight_end"]

    phase_win_map: dict[tuple[str, str], set[str]] = {}
    alive_winner: dict[int, str] = {}

    for round_item in ordered_rounds:
        round_result = result_map[round_item.index] if round_item.index in result_map else None
        round_fight_ends = [at_ms for at_ms in fight_ends if round_item.start_ms <= at_ms < round_item.end_ms]
        cutoff_ms = round_fight_ends[-1] if round_fight_ends else round_item.end_ms

        alive_state: dict[str, bool] = {}
        for event in sorted_events:
            if event.at_ms < round_item.start_ms or event.at_ms > cutoff_ms:
                continue
            if event.event_type == "PlayerRespawn":
                alive_state[event.player_id] = True
            elif event.event_type == "PlayerDeath":
                alive_state[event.player_id] = False

        eliminated = [
            team
            for team in active_teams
            if all(player_id in alive_state and alive_state[player_id] is False for player_id in team.player_ids)
        ]
        if len(eliminated) == 1:
            survivor = active_teams[1] if eliminated[0].team_id == active_teams[0].team_id else active_teams[0]
            if any(player_id in alive_state and alive_state[player_id] is True for player_id in survivor.player_ids):
                alive_winner[round_item.index] = survivor.team_id
                if (
                    round_result is not None
                    and round_result.winner_team_id is not None
                    and round_result.end_reason == "killed_all"
                    and round_result.phase
                ):
                    key = (round_result.phase, round_result.winner_team_id)
                    if key not in phase_win_map:
                        phase_win_map[key] = set()
                    phase_win_map[key].add(survivor.team_id)

    confirmed_map: dict[tuple[str, str], str] = {
        key: next(iter(candidates)) for key, candidates in phase_win_map.items() if len(candidates) == 1
    }

    phase_attack: dict[str, str] = {}
    for bomb_event in stats.bomb_events:
        if bomb_event.stage != "placed":
            continue
        if bomb_event.player_id not in player_team_map:
            continue
        team_id = player_team_map[bomb_event.player_id]
        matched_round = next(
            (
                round_item
                for round_item in ordered_rounds
                if round_item.start_ms <= bomb_event.at_ms < round_item.end_ms
            ),
            None,
        )
        if matched_round is not None and matched_round.index in result_map:
            phase = result_map[matched_round.index].phase
            if phase:
                phase_attack[phase] = team_id

    # 无安包事件时按详情终局攻守回推半场攻防归属
    phases_present = {
        result_map[round_item.index].phase
        for round_item in ordered_rounds
        if round_item.index in result_map and result_map[round_item.index].phase
    }
    if "first_half" not in phase_attack and "second_half" not in phase_attack:
        detail_attack_id = next(
            (team_id for team_id in team_ids if team_id in detail_team_side and detail_team_side[team_id] == "attack"),
            None,
        )
        if detail_attack_id is not None:
            final_half = "second_half" if "second_half" in phases_present else "first_half"
            phase_attack[final_half] = detail_attack_id

    if "first_half" in phase_attack and "second_half" not in phase_attack:
        phase_attack["second_half"] = _other_team_id(team_ids, phase_attack["first_half"])
    elif "second_half" in phase_attack and "first_half" not in phase_attack:
        phase_attack["first_half"] = _other_team_id(team_ids, phase_attack["second_half"])

    if "first_half_extra" in phase_attack and "second_half_extra" not in phase_attack:
        phase_attack["second_half_extra"] = _other_team_id(team_ids, phase_attack["first_half_extra"])
    elif "second_half_extra" in phase_attack and "first_half_extra" not in phase_attack:
        phase_attack["first_half_extra"] = _other_team_id(team_ids, phase_attack["second_half_extra"])
    elif "first_half" in phase_attack:
        if "first_half_extra" not in phase_attack:
            phase_attack["first_half_extra"] = phase_attack["first_half"]
        if "second_half_extra" not in phase_attack:
            phase_attack["second_half_extra"] = _other_team_id(team_ids, phase_attack["first_half"])

    resolved: list[_ResolvedRound] = []
    for round_item in ordered_rounds:
        round_result = result_map[round_item.index] if round_item.index in result_map else None
        phase = round_result.phase if round_result is not None and round_result.phase else "first_half"
        reason = round_result.end_reason if round_result is not None else ""
        raw_winner = round_result.winner_team_id if round_result is not None else None

        attack_team_id = phase_attack[phase] if phase in phase_attack else None
        defense_team_id = _other_team_id(team_ids, attack_team_id) if attack_team_id is not None else None

        winner_team_id: str | None = None
        if raw_winner is not None and (phase, raw_winner) in confirmed_map:
            winner_team_id = confirmed_map[(phase, raw_winner)]
        if winner_team_id is None and round_item.index in alive_winner:
            winner_team_id = alive_winner[round_item.index]
        if winner_team_id is None and reason == "bombed" and attack_team_id is not None:
            winner_team_id = attack_team_id
        if winner_team_id is None and reason in ("removed", "timeout") and defense_team_id is not None:
            winner_team_id = defense_team_id

        winner_side = ""
        if winner_team_id is not None:
            if winner_team_id == attack_team_id:
                winner_side = "attack"
            elif winner_team_id == defense_team_id:
                winner_side = "defense"

        resolved.append(
            _ResolvedRound(
                index=round_item.index,
                start_ms=round_item.start_ms,
                end_ms=round_item.end_ms,
                phase=phase,
                reason=reason,
                attack_team_id=attack_team_id,
                defense_team_id=defense_team_id,
                winner_team_id=winner_team_id,
                winner_side=winner_side,
                players=round_item.players,
            )
        )
    return resolved


def _extract_detail_maps(
    detail: DakanuMatchDetail | None,
) -> tuple[dict[str, DakanuMatchPlayer], dict[str, str], str]:
    detail_players: dict[str, DakanuMatchPlayer] = {}
    detail_team_side: dict[str, str] = {}
    match_mode = ""
    if detail is None:
        return detail_players, detail_team_side, match_mode
    match_mode = detail.matchMode
    for team in detail.teams:
        raw_id = team.id
        numeric_id = raw_id.split("_")[-1] if "_" in raw_id else raw_id
        if team.side:
            detail_team_side[numeric_id] = team.side
        for player in team.players:
            detail_players[player.playerId] = player
    return detail_players, detail_team_side, match_mode


def _resolve_summary_side(
    team_id: str,
    default_side: str,
    detail_team_side: dict[str, str],
    resolved_rounds: list[_ResolvedRound],
) -> str:
    if team_id in detail_team_side:
        return detail_team_side[team_id]
    if resolved_rounds:
        last_round = resolved_rounds[-1]
        if last_round.attack_team_id == team_id:
            return "attack"
        if last_round.defense_team_id == team_id:
            return "defense"
    return default_side


def _build_team_summary(
    team: DakanuStatsTeam,
    label: str,
    side: str,
    wins: int,
    opponent_wins: int,
    stats_players: dict[str, DakanuStatsPlayer],
    detail_players: dict[str, DakanuMatchPlayer],
    overall_accuracy: dict[str, DakanuStatsAccuracy],
    role_uris: dict[int, str],
    faction_def_uri: str,
    faction_atk_uri: str,
) -> _TeamSummaryBundle:
    sortable_rows: list[tuple[int, int, int, str, MatchAnalysisPlayerRow]] = []
    for player_id in team.player_ids:
        stats_player = stats_players[player_id] if player_id in stats_players else None
        detail_player = detail_players[player_id] if player_id in detail_players else None
        acc_item = overall_accuracy[player_id] if player_id in overall_accuracy else None
        observed = stats_player.observed_scores if stats_player is not None else None

        role_id: int | None = None
        if detail_player is not None and detail_player.roleId > 0:
            role_id = detail_player.roleId
        elif stats_player is not None and stats_player.role_id is not None and stats_player.role_id > 0:
            role_id = stats_player.role_id
        role_uri = role_uris[role_id] if role_id is not None and role_id in role_uris else ""

        if detail_player is not None:
            nickname = detail_player.nickname
            kills = detail_player.kills
            deaths = detail_player.deaths
            assists = detail_player.assists
            damage = detail_player.damage
            total_score = detail_player.score
            personal_score = (
                detail_player.personalScore
                if detail_player.personalScore is not None
                else (round(observed.personal_score) if observed is not None else 0)
            )
            strategy_score = (
                detail_player.strategyScore
                if detail_player.strategyScore is not None
                else (round(observed.strategy_score) if observed is not None else 0)
            )
            teamwork_score = (
                detail_player.teamworkScore
                if detail_player.teamworkScore is not None
                else (round(observed.teamwork_score) if observed is not None else 0)
            )
            is_mvp = detail_player.mvp
            is_svp = detail_player.svp
        else:
            nickname = stats_player.nickname if stats_player is not None and stats_player.nickname else player_id
            kills = stats_player.kills if stats_player is not None else 0
            deaths = stats_player.deaths if stats_player is not None else 0
            assists = stats_player.assists if stats_player is not None else 0
            damage = stats_player.damage if stats_player is not None else 0
            total_score = round(observed.score) if observed is not None else 0
            personal_score = round(observed.personal_score) if observed is not None else 0
            strategy_score = round(observed.strategy_score) if observed is not None else 0
            teamwork_score = round(observed.teamwork_score) if observed is not None else 0
            is_mvp = False
            is_svp = False

        row = MatchAnalysisPlayerRow(
            nickname=nickname,
            role_uri=role_uri,
            kills=kills,
            deaths=deaths,
            assists=assists,
            damage=damage,
            accuracy=_format_percent(acc_item.projectile_accuracy if acc_item is not None else None),
            headshot_rate=_format_percent(acc_item.headshot_rate if acc_item is not None else None),
            personal_score=personal_score,
            strategy_score=strategy_score,
            teamwork_score=teamwork_score,
            total_score=total_score,
            mvp=is_mvp,
            svp=is_svp,
        )
        sortable_rows.append((-total_score, -kills, deaths, player_id, row))

    sortable_rows.sort(key=lambda item: (item[0], item[1], item[2]))
    is_defense = side == "defense"
    is_winner = wins > opponent_wins
    result_label = "胜" if is_winner else ("平" if wins == opponent_wins else "负")
    summary = MatchAnalysisTeamSummary(
        label=label,
        theme="blue" if is_defense else "red",
        faction_label="欧泊" if is_defense else "剪刀手",
        faction_uri=faction_def_uri if is_defense else faction_atk_uri,
        wins=wins,
        is_winner=is_winner,
        result_label=result_label,
        players=tuple(item[4] for item in sortable_rows),
    )
    player_order = tuple(item[3] for item in sortable_rows)
    return _TeamSummaryBundle(summary=summary, player_order=player_order)


def _build_round_team_col(
    team_label: str,
    player_order: tuple[str, ...],
    side: str,
    is_winner: bool,
    round_index: int,
    round_player_map: dict[str, DakanuStatsRoundPlayer],
    round_accuracy: dict[tuple[int, str], DakanuStatsAccuracy],
    stats_players: dict[str, DakanuStatsPlayer],
    detail_players: dict[str, DakanuMatchPlayer],
    role_resolver: Callable[[str, int], int | None],
    role_uris: dict[int, str],
) -> MatchAnalysisRoundTeamCol:
    is_attack = side == "attack"
    rows: list[MatchAnalysisRoundPlayerRow] = []
    for player_id in player_order:
        round_player = round_player_map[player_id] if player_id in round_player_map else None
        acc_key = (round_index, player_id)
        acc_item = round_accuracy[acc_key] if acc_key in round_accuracy else None
        stats_player = stats_players[player_id] if player_id in stats_players else None
        detail_player = detail_players[player_id] if player_id in detail_players else None

        if detail_player is not None:
            nickname = detail_player.nickname
        elif stats_player is not None and stats_player.nickname:
            nickname = stats_player.nickname
        else:
            nickname = player_id

        role_id = role_resolver(player_id, round_index)
        if role_id is None and detail_player is not None and detail_player.roleId > 0:
            role_id = detail_player.roleId
        if role_id is None and stats_player is not None:
            role_id = stats_player.role_id
        role_uri = role_uris[role_id] if role_id is not None and role_id in role_uris else ""

        kills = round_player.kills if round_player is not None else 0
        deaths = round_player.deaths if round_player is not None else 0
        assists = round_player.assists if round_player is not None else 0
        damage = round_player.damage if round_player is not None else 0

        rows.append(
            MatchAnalysisRoundPlayerRow(
                nickname=nickname,
                role_uri=role_uri,
                kills=kills,
                deaths=deaths,
                assists=assists,
                damage=damage,
                accuracy=_format_percent(acc_item.projectile_accuracy if acc_item is not None else None),
                headshot_rate=_format_percent(acc_item.headshot_rate if acc_item is not None else None),
                is_dead=deaths > 0,
            )
        )
    return MatchAnalysisRoundTeamCol(
        team_label=team_label,
        side_label="进攻" if is_attack else "防守",
        theme="red" if is_attack else "blue",
        is_winner=is_winner,
        players=tuple(rows),
    )


async def _fetch_optional_match_detail(room_id: str) -> DakanuMatchDetail | None:
    try:
        return await get_match_detail(None, room_id)
    except DakanuError as exc:
        logger.warning(f"[卡拉彼丘·对局分析] 获取对局 {room_id} 补充详情失败，仅使用回放统计：{exc}")
        return None


async def build_match_analysis_card(room_id: str) -> bytes:
    """拉取单场对局的回放统计与详情，并渲染为对局分析 PNG 卡片。"""
    stats, detail = await asyncio.gather(
        get_match_statistics(room_id),
        _fetch_optional_match_detail(room_id),
    )

    active_team_list = [team for team in stats.teams if team.team_id not in _OBSERVER_TEAM_IDS and team.player_ids]
    if len(active_team_list) < 2:
        raise DakanuError("该对局暂无完整的双方统计数据。")

    detail_players, detail_team_side, match_mode = _extract_detail_maps(detail)

    def team_sort_key(team: DakanuStatsTeam) -> int:
        if team.team_id in detail_team_side:
            if detail_team_side[team.team_id] == "defense":
                return 0
            if detail_team_side[team.team_id] == "attack":
                return 1
        return int(team.team_id) if team.team_id.isdigit() else 9

    active_team_list.sort(key=team_sort_key)
    team_a = active_team_list[0]
    team_b = active_team_list[1]
    active_teams = (team_a, team_b)

    resolved_rounds = _resolve_rounds(stats, active_teams, detail_team_side)
    role_resolver = _build_role_resolver(stats)

    stats_players: dict[str, DakanuStatsPlayer] = {player.player_id: player for player in stats.players}
    overall_accuracy: dict[str, DakanuStatsAccuracy] = {item.player_id: item for item in stats.overall_accuracy}
    round_accuracy: dict[tuple[int, str], DakanuStatsAccuracy] = {}
    for round_acc in stats.round_accuracy:
        for item in round_acc.players:
            round_accuracy[(round_acc.index, item.player_id)] = item

    role_ids: set[int] = set()
    for team in active_teams:
        for player_id in team.player_ids:
            detail_player = detail_players[player_id] if player_id in detail_players else None
            if detail_player is not None and detail_player.roleId > 0:
                role_ids.add(detail_player.roleId)
            if player_id in stats_players:
                fallback_id = stats_players[player_id].role_id
                if fallback_id is not None and fallback_id > 0:
                    role_ids.add(fallback_id)
            for round_item in resolved_rounds:
                resolved_id = role_resolver(player_id, round_item.index)
                if resolved_id is not None and resolved_id > 0:
                    role_ids.add(resolved_id)

    role_uris, faction_def_uri, faction_atk_uri = await asyncio.gather(
        _load_role_uris(role_ids),
        to_thread(_load_tinted_faction_uri)(local_faction_image(1), _BLUE_RGB),
        to_thread(_load_tinted_faction_uri)(local_faction_image(2), _RED_RGB),
    )

    wins_a = sum(1 for round_item in resolved_rounds if round_item.winner_team_id == team_a.team_id)
    wins_b = sum(1 for round_item in resolved_rounds if round_item.winner_team_id == team_b.team_id)

    side_a = _resolve_summary_side(team_a.team_id, "defense", detail_team_side, resolved_rounds)
    side_b = _resolve_summary_side(team_b.team_id, "attack", detail_team_side, resolved_rounds)

    bundle_a = _build_team_summary(
        team_a,
        "A队",
        side_a,
        wins_a,
        wins_b,
        stats_players,
        detail_players,
        overall_accuracy,
        role_uris,
        faction_def_uri,
        faction_atk_uri,
    )
    bundle_b = _build_team_summary(
        team_b,
        "B队",
        side_b,
        wins_b,
        wins_a,
        stats_players,
        detail_players,
        overall_accuracy,
        role_uris,
        faction_def_uri,
        faction_atk_uri,
    )

    strip_items: list[MatchAnalysisStripItem] = []
    previous_phase: str | None = None
    for round_item in resolved_rounds:
        divider_before = previous_phase is not None and round_item.phase != previous_phase
        previous_phase = round_item.phase
        winner_slot = ""
        if round_item.winner_team_id == team_a.team_id:
            winner_slot = "a"
        elif round_item.winner_team_id == team_b.team_id:
            winner_slot = "b"
        winner_color = _RED_COLOR if round_item.winner_side == "attack" else _BLUE_COLOR
        strip_items.append(
            MatchAnalysisStripItem(
                round_index=round_item.index,
                divider_before=divider_before,
                winner_slot=winner_slot,
                reason=round_item.reason,
                winner_color=winner_color,
            )
        )

    cumulative_a = 0
    cumulative_b = 0
    round_cards: list[MatchAnalysisRoundItem] = []
    for round_item in resolved_rounds:
        if round_item.winner_team_id == team_a.team_id:
            cumulative_a += 1
        elif round_item.winner_team_id == team_b.team_id:
            cumulative_b += 1

        if round_item.attack_team_id is not None:
            round_side_a = "attack" if round_item.attack_team_id == team_a.team_id else "defense"
            round_side_b = "attack" if round_item.attack_team_id == team_b.team_id else "defense"
        else:
            round_side_a = side_a
            round_side_b = side_b

        round_player_map: dict[str, DakanuStatsRoundPlayer] = {
            player.player_id: player for player in round_item.players
        }
        phase_label = _PHASE_LABELS[round_item.phase] if round_item.phase in _PHASE_LABELS else round_item.phase
        round_cards.append(
            MatchAnalysisRoundItem(
                round_index=round_item.index,
                phase_label=phase_label,
                score_text=f"{cumulative_a} : {cumulative_b}",
                duration_text=_format_duration_ms(round_item.end_ms - round_item.start_ms),
                team_a=_build_round_team_col(
                    "A队",
                    bundle_a.player_order,
                    round_side_a,
                    round_item.winner_team_id == team_a.team_id,
                    round_item.index,
                    round_player_map,
                    round_accuracy,
                    stats_players,
                    detail_players,
                    role_resolver,
                    role_uris,
                ),
                team_b=_build_round_team_col(
                    "B队",
                    bundle_b.player_order,
                    round_side_b,
                    round_item.winner_team_id == team_b.team_id,
                    round_item.index,
                    round_player_map,
                    round_accuracy,
                    stats_players,
                    detail_players,
                    role_resolver,
                    role_uris,
                ),
            )
        )

    mode_label = _MODE_LABELS[match_mode] if match_mode in _MODE_LABELS else "对局"
    context = MatchAnalysisTemplateContext(
        room_id=room_id,
        mode_label=mode_label,
        duration_text=_format_duration_ms(stats.duration_ms),
        team_a=bundle_a.summary,
        team_b=bundle_b.summary,
        strip_items=tuple(strip_items),
        rounds=tuple(round_cards),
    )
    return await render_match_analysis_card(context)
