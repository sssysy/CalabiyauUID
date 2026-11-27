"""Dakanu Pydantic 模型基类与常用字段归一化标注。"""

from __future__ import annotations

from typing import Any, TypeVar, Annotated

from pydantic import BaseModel, ConfigDict, BeforeValidator, ValidationError

ItemT = TypeVar("ItemT", bound=BaseModel)


class DakanuModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


def _none_to_zero_int(value: Any) -> Any:
    return 0 if value is None else value


def _none_to_zero_float(value: Any) -> Any:
    return 0.0 if value is None else value


def _none_to_empty_str(value: Any) -> Any:
    return "" if value is None else value


def _none_to_false(value: Any) -> Any:
    return False if value is None else value


def _coerce_id_str(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return value


def _coerce_opt_id_str(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _positive_int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _opt_int_strict(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _opt_float_strict(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def parse_tolerant_list(model_cls: type[ItemT], raw: Any) -> list[ItemT]:
    """宽容解析模型列表：跳过单条畸形记录，避免个别坏条目打断整页结果。"""
    if not isinstance(raw, list):
        return []
    items: list[ItemT] = []
    for entry in raw:
        try:
            items.append(model_cls.model_validate(entry))
        except ValidationError:
            continue
    return items


ZeroInt = Annotated[int, BeforeValidator(_none_to_zero_int)]
ZeroFloat = Annotated[float, BeforeValidator(_none_to_zero_float)]
EmptyStr = Annotated[str, BeforeValidator(_none_to_empty_str)]
FalseBool = Annotated[bool, BeforeValidator(_none_to_false)]
IdStr = Annotated[str, BeforeValidator(_coerce_id_str)]
OptIdStr = Annotated[str | None, BeforeValidator(_coerce_opt_id_str)]
PositiveIntOrNone = Annotated[int | None, BeforeValidator(_positive_int_or_none)]
OptInt = Annotated[int | None, BeforeValidator(_opt_int_strict)]
OptFloat = Annotated[float | None, BeforeValidator(_opt_float_strict)]
