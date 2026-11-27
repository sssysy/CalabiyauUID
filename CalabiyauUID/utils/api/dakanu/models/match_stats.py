"""Dakanu 对局回放解析统计模型。"""

from __future__ import annotations

from typing import Any

from pydantic import Field, ConfigDict, ValidationError, model_validator

from .base import (
    IdStr,
    OptInt,
    ZeroInt,
    EmptyStr,
    OptFloat,
    OptIdStr,
    ZeroFloat,
    DakanuModel,
    PositiveIntOrNone,
    parse_tolerant_list,
)


class _FrozenStatsModel(DakanuModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore", frozen=True)


class DakanuStatsObservedScores(_FrozenStatsModel):
    score: ZeroFloat = 0.0
    personal_score: ZeroFloat = 0.0
    strategy_score: ZeroFloat = 0.0
    teamwork_score: ZeroFloat = 0.0


def _parse_observed_scores(raw: Any) -> DakanuStatsObservedScores | None:
    if not isinstance(raw, dict):
        return None
    keys = ("score", "personal_score", "strategy_score", "teamwork_score")
    if not any(isinstance(raw.get(k), (int, float)) and not isinstance(raw.get(k), bool) for k in keys):
        return None
    return DakanuStatsObservedScores.model_validate(raw)


class DakanuStatsPlayer(_FrozenStatsModel):
    player_id: IdStr
    nickname: str = ""
    team_id: EmptyStr = ""
    role_id: PositiveIntOrNone = None
    kills: ZeroInt = 0
    deaths: ZeroInt = 0
    assists: ZeroInt = 0
    knockdowns: ZeroInt = 0
    damage: ZeroInt = 0
    head_hits: ZeroInt = 0
    observed_scores: DakanuStatsObservedScores | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        copied = dict(data)
        raw_pid = copied.get("player_id")
        pid = str(raw_pid).strip() if isinstance(raw_pid, (int, str)) and not isinstance(raw_pid, bool) else ""
        if not isinstance(copied.get("nickname"), str):
            copied["nickname"] = pid
        if isinstance(copied.get("team_id"), int) and not isinstance(copied["team_id"], bool):
            copied["team_id"] = str(copied["team_id"])
        copied["observed_scores"] = _parse_observed_scores(copied.get("observed_scores"))
        return copied


class DakanuStatsTeam(_FrozenStatsModel):
    team_id: IdStr
    player_ids: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict) or not isinstance(data.get("player_ids"), list):
            return data
        pids: list[str] = []
        for raw_pid in data["player_ids"]:
            if isinstance(raw_pid, str) and raw_pid.strip():
                pids.append(raw_pid.strip())
            elif isinstance(raw_pid, int) and not isinstance(raw_pid, bool):
                pids.append(str(raw_pid))
        return {**data, "player_ids": tuple(pids)}


class DakanuStatsRoundPlayer(_FrozenStatsModel):
    player_id: IdStr
    kills: ZeroInt = 0
    deaths: ZeroInt = 0
    assists: ZeroInt = 0
    knockdowns: ZeroInt = 0
    damage: ZeroInt = 0
    head_hits: ZeroInt = 0


class DakanuStatsRound(_FrozenStatsModel):
    index: int
    start_ms: int
    end_ms: int
    players: tuple[DakanuStatsRoundPlayer, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        return {**data, "players": tuple(parse_tolerant_list(DakanuStatsRoundPlayer, data.get("players")))}


class DakanuStatsRoundResult(_FrozenStatsModel):
    round_index: int = Field(alias="round")
    winner_team_id: OptIdStr = None
    end_reason: EmptyStr = ""
    phase: EmptyStr = ""


class DakanuStatsEvent(_FrozenStatsModel):
    event_type: str = Field(alias="type")
    at_ms: int
    round_index: OptInt = Field(default=None, alias="round")
    player_id: IdStr


class DakanuStatsBombEvent(_FrozenStatsModel):
    at_ms: int
    round_index: OptInt = Field(default=None, alias="round")
    player_id: IdStr
    stage: str


class DakanuStatsPhasePoint(_FrozenStatsModel):
    at_ms: int
    phase: str


class DakanuStatsRoleEvent(_FrozenStatsModel):
    at_ms: int
    order: int = 10**12
    player_id: str
    role_id: int | None = None


class DakanuStatsAccuracy(_FrozenStatsModel):
    player_id: IdStr
    projectile_accuracy: OptFloat = Field(default=None, alias="observed_projectile_accuracy")
    headshot_rate: OptFloat = Field(default=None, alias="observed_headshot_rate")


class DakanuStatsRoundAccuracy(_FrozenStatsModel):
    index: int
    players: tuple[DakanuStatsAccuracy, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        return {**data, "players": tuple(parse_tolerant_list(DakanuStatsAccuracy, data.get("players")))}


class DakanuMatchStatistics(_FrozenStatsModel):
    room_id: IdStr
    duration_ms: ZeroInt = 0
    teams: tuple[DakanuStatsTeam, ...] = ()
    players: tuple[DakanuStatsPlayer, ...] = ()
    rounds: tuple[DakanuStatsRound, ...] = ()
    round_results: tuple[DakanuStatsRoundResult, ...] = ()
    events: tuple[DakanuStatsEvent, ...] = ()
    bomb_events: tuple[DakanuStatsBombEvent, ...] = ()
    phase_timeline: tuple[DakanuStatsPhasePoint, ...] = ()
    role_timeline: tuple[DakanuStatsRoleEvent, ...] = ()
    overall_accuracy: tuple[DakanuStatsAccuracy, ...] = ()
    round_accuracy: tuple[DakanuStatsRoundAccuracy, ...] = ()


class DakanuMatchStatisticsPayload(_FrozenStatsModel):
    stats: DakanuMatchStatistics
    raw_json: str


def _extract_role_event(raw: Any, fallback_player_id: str = "") -> DakanuStatsRoleEvent | None:
    if isinstance(raw, dict):
        raw_pid = raw.get("player_id")
        pid = (
            raw_pid.strip()
            if isinstance(raw_pid, str) and raw_pid.strip()
            else (str(raw_pid) if isinstance(raw_pid, int) and not isinstance(raw_pid, bool) else fallback_player_id)
        )
        at_ms = raw.get("at_ms")
        if not pid or not isinstance(at_ms, int) or isinstance(at_ms, bool) or "role_id" not in raw:
            return None
        order = raw.get("record_index")
        role_id = raw.get("role_id")
        return DakanuStatsRoleEvent(
            at_ms=at_ms,
            order=order if isinstance(order, int) and not isinstance(order, bool) else 10**12,
            player_id=pid,
            role_id=role_id if isinstance(role_id, int) and not isinstance(role_id, bool) and role_id > 0 else None,
        )
    # view=web 紧凑数组格式：[at_ms, round, record_index, player_id, role_id, ...]
    if isinstance(raw, list) and len(raw) >= 5:
        at_ms, order, raw_pid, role_id = raw[0], raw[2], raw[3], raw[4]
        pid = (
            raw_pid.strip()
            if isinstance(raw_pid, str) and raw_pid.strip()
            else (str(raw_pid) if isinstance(raw_pid, int) and not isinstance(raw_pid, bool) else fallback_player_id)
        )
        if not pid or not isinstance(at_ms, int) or isinstance(at_ms, bool):
            return None
        return DakanuStatsRoleEvent(
            at_ms=at_ms,
            order=order if isinstance(order, int) and not isinstance(order, bool) else 10**12,
            player_id=pid,
            role_id=role_id if isinstance(role_id, int) and not isinstance(role_id, bool) and role_id > 0 else None,
        )
    return None


def _parse_role_timeline(observations: dict[str, Any]) -> tuple[DakanuStatsRoleEvent, ...]:
    result: list[DakanuStatsRoleEvent] = []
    has_primary: set[str] = set()
    for item in observations.get("role_timeline") or []:
        event = _extract_role_event(item)
        if event is not None:
            result.append(event)
            has_primary.add(event.player_id)

    for key in ("growth_level_timeline", "loadout_timeline"):
        for item in observations.get(key) or []:
            event = _extract_role_event(item)
            if event is not None and event.player_id not in has_primary:
                result.append(event)

    growth_routes = observations.get("growth_routes")
    if isinstance(growth_routes, dict):
        for entry in growth_routes.get("players") or []:
            if not isinstance(entry, dict):
                continue
            raw_pid = entry.get("player_id")
            pid = (
                raw_pid.strip()
                if isinstance(raw_pid, str) and raw_pid.strip()
                else (str(raw_pid) if isinstance(raw_pid, int) and not isinstance(raw_pid, bool) else "")
            )
            if not pid or pid in has_primary:
                continue
            for ev_key in ("events", "temporary_events"):
                for raw_ev in entry.get(ev_key) or []:
                    event = _extract_role_event(raw_ev, pid)
                    if event is not None:
                        result.append(event)

    result.sort(key=lambda item: (item.at_ms, item.order))
    return tuple(result)


def parse_match_statistics(payload: Any) -> DakanuMatchStatistics | None:
    """将 `/api/match/{room_id}/statistics` JSON 载荷解析为 DakanuMatchStatistics。"""
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return None
    duration = payload.get("duration_ms")
    if not isinstance(duration, int) or isinstance(duration, bool):
        duration = payload.get("replay_length_ms")
    duration_ms = duration if isinstance(duration, int) and not isinstance(duration, bool) else 0

    rounds = sorted(parse_tolerant_list(DakanuStatsRound, payload.get("rounds")), key=lambda item: item.index)
    events = sorted(parse_tolerant_list(DakanuStatsEvent, payload.get("events")), key=lambda item: item.at_ms)

    observations = payload.get("observations") if isinstance(payload.get("observations"), dict) else {}
    attacks = observations.get("attacks") if isinstance(observations.get("attacks"), dict) else {}
    combat_only = attacks.get("combat_only") if isinstance(attacks.get("combat_only"), dict) else {}

    overall_accuracy = tuple(parse_tolerant_list(DakanuStatsAccuracy, combat_only.get("players")))
    if not overall_accuracy:
        overall_accuracy = tuple(parse_tolerant_list(DakanuStatsAccuracy, attacks.get("players")))

    try:
        return DakanuMatchStatistics.model_validate(
            {
                "room_id": payload.get("room_id"),
                "duration_ms": duration_ms,
                "teams": tuple(parse_tolerant_list(DakanuStatsTeam, payload.get("teams"))),
                "players": tuple(parse_tolerant_list(DakanuStatsPlayer, payload.get("players"))),
                "rounds": tuple(rounds),
                "round_results": tuple(parse_tolerant_list(DakanuStatsRoundResult, observations.get("round_results"))),
                "events": tuple(events),
                "bomb_events": tuple(parse_tolerant_list(DakanuStatsBombEvent, observations.get("bomb_events"))),
                "phase_timeline": tuple(parse_tolerant_list(DakanuStatsPhasePoint, combat_only.get("phase_timeline"))),
                "role_timeline": _parse_role_timeline(observations),
                "overall_accuracy": overall_accuracy,
                "round_accuracy": tuple(parse_tolerant_list(DakanuStatsRoundAccuracy, combat_only.get("rounds"))),
            }
        )
    except ValidationError:
        return None
