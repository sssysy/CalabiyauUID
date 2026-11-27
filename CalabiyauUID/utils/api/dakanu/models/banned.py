"""Dakanu 封神榜模型。"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from .base import OptInt, EmptyStr, FalseBool, DakanuModel, parse_tolerant_list


class DakanuBannedEntry(DakanuModel):
    entryKey: str
    playerId: str | None = None
    nickname: str
    avatarId: OptInt = None
    level: OptInt = None
    segment: OptInt = None
    divisionScore: OptInt = None
    matchCount: int = 1
    maskedId: EmptyStr = ""
    maskedNick: EmptyStr = ""
    matched: FalseBool = False
    confidence: EmptyStr = ""
    announcementTitle: EmptyStr = ""
    announcementUrl: EmptyStr = ""
    publishedAt: OptInt = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        copied = dict(data)
        raw_nick = copied.get("nickname")
        masked_nick = copied.get("maskedNick")
        nickname = (
            raw_nick
            if isinstance(raw_nick, str) and raw_nick
            else (masked_nick if isinstance(masked_nick, str) else "")
        )
        if not nickname:
            raise ValueError("banned entry requires nickname or maskedNick")
        copied["nickname"] = nickname
        if copied.get("matchCount") is None:
            copied["matchCount"] = 1
        return copied


class DakanuBannedResponse(DakanuModel):
    ok: bool = True
    entries: list[DakanuBannedEntry] = Field(default_factory=list)
    total: int
    offset: int
    limit: int
    hasMore: bool

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("ok") is not True or not isinstance(data.get("entries"), list):
            raise ValueError("invalid banned players payload")
        return {**data, "entries": parse_tolerant_list(DakanuBannedEntry, data["entries"])}
