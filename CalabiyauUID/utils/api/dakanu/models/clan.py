"""Dakanu 战队与战队成员名册模型。"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from .base import OptInt, EmptyStr, FalseBool, DakanuModel, parse_tolerant_list


class DakanuClanIcon(DakanuModel):
    bgId: int
    bgColor: int
    imageId: int
    imageColor: int


class DakanuClan(DakanuModel):
    clanId: str
    name: str
    level: int
    memberCount: int
    icon: DakanuClanIcon
    intro: EmptyStr = ""


class DakanuClanMember(DakanuModel):
    playerId: str
    nickname: str
    avatarId: OptInt = None
    level: OptInt = None
    position: OptInt = None
    isLeader: bool | None = None


class DakanuClanMembersResponse(DakanuModel):
    ok: bool = True
    clanId: str
    count: int
    members: list[DakanuClanMember] = Field(default_factory=list)
    source: EmptyStr = ""
    cached: FalseBool = False
    refreshing: FalseBool = False

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("ok") is not True or not isinstance(data.get("members"), list):
            raise ValueError("invalid clan members payload")
        return {**data, "members": parse_tolerant_list(DakanuClanMember, data["members"])}
