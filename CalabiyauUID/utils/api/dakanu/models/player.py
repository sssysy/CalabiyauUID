"""Dakanu 玩家档案、刷新任务、休闲数据、历史赛季与搜索建议模型。"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from .base import OptInt, ZeroInt, EmptyStr, FalseBool, ZeroFloat, DakanuModel, parse_tolerant_list
from .match import DakanuMatch


class DakanuMedal(DakanuModel):
    id: int | None = None
    axis: list[int] | None = None
    zoomScale: float | None = None
    rotateScale: float | None = None
    levelFlip: FalseBool = False
    level: int | None = None


class DakanuPlayerTag(DakanuModel):
    id: EmptyStr = ""
    label: EmptyStr = ""
    tone: EmptyStr = ""
    description: EmptyStr = ""


class DakanuPlayer(DakanuModel):
    id: str
    nickname: str
    clanId: EmptyStr = ""
    previousNames: list[str] = Field(default_factory=list)
    level: ZeroInt = 0
    exp: ZeroInt = 0
    laud: ZeroInt = 0
    avatarId: ZeroInt = 0
    borderId: ZeroInt = 0
    privacyStatus: EmptyStr = ""
    accountVerified: FalseBool = False
    medals: list[DakanuMedal | int] = Field(default_factory=list)
    tags: list[DakanuPlayerTag] = Field(default_factory=list)


class DakanuPlayerSuggestion(DakanuModel):
    playerId: str
    nickname: str
    matchedName: str
    matchedBy: str
    level: OptInt = None
    icon: OptInt = None
    exact: bool
    indexed: bool

    @field_validator("playerId")
    @classmethod
    def _validate_player_id(cls, value: str) -> str:
        if not value or not value.isascii() or not value.isdigit():
            raise ValueError("playerId must be ASCII digits")
        return value


class DakanuPresence(DakanuModel):
    state: EmptyStr = ""
    onlineStatus: int | str | None = None
    lastOnlineAt: OptInt = None
    lastActiveAt: OptInt = None
    statusText: str | None = None
    regionLabel: str | None = None
    leisureScore: OptInt = None
    leisureSegment: OptInt = None
    stars: OptInt = None
    winGames: OptInt = None
    mvpCount: OptInt = None
    totalGames: OptInt = None


class DakanuRank(DakanuModel):
    segment: ZeroInt = 0
    topSegment: ZeroInt = 0
    historicalSegment: ZeroInt = 0
    historicalSegmentSeason: ZeroInt = 0
    historicalSegmentPos: OptInt = None
    divisionScore: ZeroInt = 0
    topDivisionScore: ZeroInt = 0
    gradeScore: ZeroInt = 0
    topGradeScore: ZeroInt = 0
    rankPos: OptInt = None
    topRankPos: OptInt = None
    likeCount: ZeroInt = 0


class DakanuSummary(DakanuModel):
    rounds: int
    wins: int
    losses: int
    winRate: ZeroFloat = 0.0
    kills: ZeroInt = 0
    assists: ZeroInt = 0
    deaths: ZeroInt = 0
    kd: ZeroFloat = 0.0
    kda: ZeroFloat = 0.0
    damage: ZeroInt = 0
    avgDamage: ZeroFloat = 0.0
    roundAveDamage: ZeroFloat = 0.0
    avgKill: ZeroFloat = 0.0
    avgAssist: ZeroFloat = 0.0
    avgDeath: ZeroFloat = 0.0
    mvpCount: ZeroInt = 0
    mvpRate: ZeroFloat = 0.0
    headshotRate: ZeroFloat = 0.0


class DakanuMode(DakanuModel):
    mode: str
    label: str
    rounds: int
    wins: int
    winRate: ZeroFloat = 0.0
    kd: ZeroFloat = 0.0
    kills: int | None = None
    assists: int | None = None
    deaths: int | None = None
    damage: int | None = None
    kda: float | None = None
    avgDamage: ZeroFloat = 0.0
    roundAveDamage: ZeroFloat = 0.0
    avgKill: ZeroFloat = 0.0
    avgAssist: float | None = None
    avgDeath: float | None = None
    headshotRate: ZeroFloat = 0.0
    mvpCount: int | None = None
    mvpRate: ZeroFloat = 0.0


class DakanuRole(DakanuModel):
    roleId: int
    name: str
    count: int
    wins: int
    winRate: ZeroFloat = 0.0
    kills: ZeroInt = 0
    deaths: ZeroInt = 0
    kd: ZeroFloat = 0.0
    damage: ZeroInt = 0
    avgDamage: ZeroFloat = 0.0
    maxKill: ZeroInt = 0
    maxDamage: ZeroInt = 0


class DakanuMeta(DakanuModel):
    cached: FalseBool = False
    source: EmptyStr = ""
    currentSeason: EmptyStr = ""
    matchesTotal: ZeroInt = 0
    detailsAvailable: ZeroInt = 0
    warnings: list[str] = Field(default_factory=list)
    fetchedAt: ZeroInt = 0
    stale: str | None = None
    currentSeasonStartedAt: OptInt = None
    observedMatches: ZeroInt = 0
    lastCheckedAt: ZeroInt = 0


class DakanuTeamUp(DakanuModel):
    playerId: str
    nickname: str
    avatarId: int
    teamedGames: int
    teamedWins: int
    teamedLosses: int
    teamedDraws: int
    teamedWinRate: float
    lastWinAt: OptInt = None
    latestRoomId: str | None = None


class DakanuRival(DakanuModel):
    playerId: str
    nickname: str
    avatarId: int
    games: int
    wins: int
    losses: int
    draws: int
    winRate: float
    lastPlayedAt: OptInt = None
    latestRoomId: str | None = None


class DakanuProfile(DakanuModel):
    player: DakanuPlayer
    presence: DakanuPresence
    rank: DakanuRank
    summary: DakanuSummary
    modes: list[DakanuMode] = Field(default_factory=list)
    roles: list[DakanuRole] = Field(default_factory=list)
    matches: list[DakanuMatch] = Field(default_factory=list)
    historyMatches: list[DakanuMatch] = Field(default_factory=list)
    teamUps: list[DakanuTeamUp] = Field(default_factory=list)
    rivals: list[DakanuRival] = Field(default_factory=list)
    meta: DakanuMeta


class DakanuFavoriteMode(DakanuModel):
    mode: str
    label: str


class DakanuLeisure(DakanuModel):
    playerId: str | None = None
    seasonId: OptInt = None
    seasonLabel: str | None = None
    score: OptInt = None
    segment: OptInt = None
    star: OptInt = None
    starScore: OptInt = None
    battles: OptInt = None
    wins: OptInt = None
    winRate: float | None = None
    mvpCount: OptInt = None
    avgPerformanceScore: float | None = None
    favoriteModes: list[DakanuFavoriteMode] = Field(default_factory=list)
    favoriteRoles: list[int] = Field(default_factory=list)


class DakanuRefreshError(DakanuModel):
    message: EmptyStr = ""
    code: EmptyStr = ""
    status: ZeroInt = 0


class DakanuRefreshJob(DakanuModel):
    state: EmptyStr = ""
    startedAt: OptInt = None
    finishedAt: OptInt = None
    attempt: OptInt = None
    nextAttemptAt: OptInt = None
    error: DakanuRefreshError | None = None
    warning: dict[str, str] | None = None


class DakanuSeasonRankPoint(DakanuModel):
    segment: OptInt = None
    stars: OptInt = None
    rankPosition: OptInt = None
    divisionScore: OptInt = None
    gradeScore: OptInt = None


class DakanuPlayerSeason(DakanuModel):
    seasonId: int
    seasonLabel: str
    final: DakanuSeasonRankPoint = Field(default_factory=DakanuSeasonRankPoint)
    top: DakanuSeasonRankPoint = Field(default_factory=DakanuSeasonRankPoint)
    historicalTopSegment: OptInt = None
    historicalTopPosition: OptInt = None
    superStringCount: OptInt = None
    favoriteRoles: list[int] = Field(default_factory=list)
    leisure: DakanuLeisure | None = None
    summary: DakanuSummary
    modes: list[DakanuMode] = Field(default_factory=list)
    roles: list[DakanuRole] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        copied = dict(data)
        if not isinstance(copied.get("final"), dict):
            copied["final"] = {}
        if not isinstance(copied.get("top"), dict):
            copied["top"] = {}
        raw_favs = copied.get("favoriteRoles")
        copied["favoriteRoles"] = (
            [item for item in raw_favs if isinstance(item, int) and not isinstance(item, bool)]
            if isinstance(raw_favs, list)
            else []
        )
        copied["modes"] = parse_tolerant_list(DakanuMode, copied.get("modes"))
        copied["roles"] = parse_tolerant_list(DakanuRole, copied.get("roles"))
        raw_leisure = copied.get("leisure")
        if isinstance(raw_leisure, dict):
            leisure_fields = ("score", "segment", "star", "starScore", "battles", "wins", "winRate", "mvpCount")
            if not any(raw_leisure.get(key) is not None for key in leisure_fields):
                copied["leisure"] = None
        else:
            copied["leisure"] = None
        return copied
