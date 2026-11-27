"""Dakanu 对局列表、对局详情与回放凭证模型。"""

from __future__ import annotations

import re
from typing import Any

from pydantic import Field, ConfigDict

from .base import EmptyStr, FalseBool, DakanuModel

_ROOM_ID_RE = re.compile(r"^[1-9]\d{0,19}$")


def is_valid_room_id(room_id: str) -> bool:
    """校验对局 ID 是否符合 Dakanu 规则。"""
    return bool(_ROOM_ID_RE.fullmatch(room_id))


class DakanuMatch(DakanuModel):
    roomId: str
    mode: str
    modeLabel: str
    playMode: str | None = None
    mapId: int | None = None
    roleId: int | None = None
    result: str
    myScore: int | None = None
    opponentScore: int | None = None
    durationSeconds: int | None = None
    playedAt: int | None = None
    myRanking: int | None = None
    mvp: FalseBool = False
    svp: FalseBool = False
    divisionScore: int | None = None
    divisionScoreDelta: int | None = None
    kills: int | None = None
    deaths: int | None = None
    assists: int | None = None
    teamKills: int | None = None


class DakanuMatchPlayer(DakanuModel):
    playerId: str
    nickname: str
    avatarId: int
    teamId: str
    teamLabel: str
    roleId: int
    roleName: str
    kills: int
    knockdowns: int | None = None
    assists: int
    deaths: int
    damage: int
    score: int
    personalScore: int | None = None
    strategyScore: int | None = None
    teamworkScore: int | None = None
    result: str
    mvp: bool
    svp: bool
    isTarget: bool


class DakanuMatchTeam(DakanuModel):
    id: str
    label: str
    players: list[DakanuMatchPlayer]
    side: EmptyStr = ""
    sideLabel: EmptyStr = ""


class DakanuMatchDetail(DakanuModel):
    ok: bool = True
    roomId: str
    matchMode: EmptyStr = ""
    summary: Any = None
    teams: list[DakanuMatchTeam] = Field(default_factory=list)
    rounds: list[Any] = Field(default_factory=list)
    hasDetail: FalseBool = False
    viewerPlayerId: str | None = None
    scoreboardViewerPlayerId: str | None = None
    upstreamCode: int = 0
    viewerFallback: Any = None
    cached: FalseBool = False


class DakanuReplayTicket(DakanuModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore", frozen=True)

    room_id: str
    download_url: str
    cookies: dict[str, str]
    verified: bool = False
