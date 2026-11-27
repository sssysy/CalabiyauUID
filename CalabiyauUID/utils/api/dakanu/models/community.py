"""Dakanu 游戏活跃趋势与世界频道聚合消息模型。"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from .base import OptInt, DakanuModel, parse_tolerant_list


class DakanuActivityPoint(DakanuModel):
    at: int
    index: float


class DakanuActivityEstimatePoint(DakanuModel):
    at: int
    floor: int
    gap: int
    channel: int
    daily: int
    completePlayers: int
    completeSeats: int
    partialRooms: int
    coverage: float
    active30d: int


class DakanuActivityEstimate(DakanuModel):
    updatedAt: int
    points: list[DakanuActivityEstimatePoint] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict) or not isinstance(data.get("points"), list):
            raise ValueError("invalid activity estimate payload")
        return {**data, "points": parse_tolerant_list(DakanuActivityEstimatePoint, data["points"])}


class DakanuGameActivity(DakanuModel):
    ok: bool = True
    range: str
    intervalSeconds: int
    updatedAt: int
    sparse: bool
    region: str
    estimate: DakanuActivityEstimate
    points: list[DakanuActivityPoint] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("ok") is not True or not isinstance(data.get("points"), list):
            raise ValueError("invalid game activity payload")
        return {**data, "points": parse_tolerant_list(DakanuActivityPoint, data["points"])}


class DakanuChatSelection(DakanuModel):
    channel: OptInt = None
    population: OptInt = None
    reason: str | None = None


class DakanuChatScope(DakanuModel):
    include_empty: bool
    channel_count: int
    active_channels: int
    requested_channels: int
    selected_channels: int


class DakanuChatMessage(DakanuModel):
    channel: int
    player_id: str
    nick: str
    message: str
    sent_at: int
    icon: OptInt = None
    icon_frame: OptInt = None
    vc_border_id: OptInt = None
    bubble_id: OptInt = None
    level: OptInt = None
    target_id: str | None = None


class DakanuChatAggregate(DakanuModel):
    ok: bool = True
    generated_at: int
    scope: DakanuChatScope
    strategy: str
    selection: DakanuChatSelection
    messages: list[DakanuChatMessage] = Field(default_factory=list)
    count: int
    elapsed_seconds: float

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("ok") is not True or not isinstance(data.get("messages"), list):
            raise ValueError("invalid chat aggregate payload")
        return {**data, "messages": parse_tolerant_list(DakanuChatMessage, data["messages"])}
