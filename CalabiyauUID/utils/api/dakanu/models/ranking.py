"""Dakanu 排位排行榜、奇点底分、赛季目录与超弦体榜单模型。"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from .base import OptInt, OptFloat, DakanuModel, parse_tolerant_list


class DakanuRankType(DakanuModel):
    code: int
    key: str
    label: str


class DakanuRankingEntry(DakanuModel):
    position: int
    playerId: str
    nickname: str
    avatarId: int
    level: int
    borderId: int
    segment: OptInt = None
    wins: OptInt = None
    totalGames: OptInt = None
    roles: list[int] = Field(default_factory=list)
    score: int
    previousScore: OptInt = None
    scoreDelta: OptInt = None
    region: str | None = None
    province: str | None = None
    city: str | None = None
    cityCode: OptInt = None

    @field_validator("roles", mode="before")
    @classmethod
    def _filter_roles(cls, value: Any) -> list[int]:
        if not isinstance(value, list):
            raise ValueError("roles must be a list")
        return [item for item in value if isinstance(item, int) and not isinstance(item, bool)]


class DakanuRankingsBoard(DakanuModel):
    ok: bool = True
    scope: str
    rankType: DakanuRankType
    metricLabel: str
    start: int
    end: int
    total: int
    day: str
    compareDay: str | None = None
    updatedAt: int
    cachedAt: OptInt = None
    entries: list[DakanuRankingEntry] = Field(default_factory=list)
    seasonApplied: bool | None = None
    seasonLabel: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("ok") is not True or not isinstance(data.get("entries"), list):
            raise ValueError("invalid rankings board payload")
        copied = dict(data)
        copied["entries"] = parse_tolerant_list(DakanuRankingEntry, data["entries"])
        raw_query = data.get("query")
        if isinstance(raw_query, dict) and isinstance(raw_query.get("seasonApplied"), bool):
            copied["seasonApplied"] = raw_query["seasonApplied"]
        return copied


class DakanuRankingFloorCurrent(DakanuModel):
    day: str
    score: int
    position: int
    observedAt: int
    source: str


class DakanuRankingFloor(DakanuModel):
    ok: bool = True
    region: str
    seasonId: int
    current: DakanuRankingFloorCurrent
    yesterdayDelta: OptInt = None


class DakanuRankedSeason(DakanuModel):
    season_id: int
    label: str
    current: bool


class DakanuCurrentSeason(DakanuModel):
    ok: bool = True
    ranked_season: DakanuRankedSeason


class DakanuRankingSeasonItem(DakanuModel):
    season_id: int
    label: str
    current: bool
    rank_types: list[int] = Field(default_factory=list)
    fetched_at: OptInt = None

    @field_validator("rank_types", mode="before")
    @classmethod
    def _filter_rank_types(cls, value: Any) -> list[int]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, int) and not isinstance(item, bool)]


class DakanuRankingSeasons(DakanuModel):
    ok: bool = True
    current: DakanuRankedSeason
    seasons: list[DakanuRankingSeasonItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("ok") is not True or not isinstance(data.get("seasons"), list):
            raise ValueError("invalid ranking seasons payload")
        return {**data, "seasons": parse_tolerant_list(DakanuRankingSeasonItem, data["seasons"])}


class DakanuRolesRankingEntry(DakanuModel):
    roleId: int
    games: int
    wins: int
    winRate: float
    appearanceRate: float
    players: int
    pickRate: float
    previousWinRate: OptFloat = None
    winRateDelta: OptFloat = None
    previousAppearanceRate: OptFloat = None
    appearanceRateDelta: OptFloat = None


class DakanuRolesRankingBoard(DakanuModel):
    ok: bool = True
    scope: str
    rankedOnly: bool
    minGames: int
    day: str
    compareDay: str | None = None
    updatedAt: int
    coveredMatches: int
    entries: list[DakanuRolesRankingEntry] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("ok") is not True or not isinstance(data.get("entries"), list):
            raise ValueError("invalid roles ranking board payload")
        return {**data, "entries": parse_tolerant_list(DakanuRolesRankingEntry, data["entries"])}
