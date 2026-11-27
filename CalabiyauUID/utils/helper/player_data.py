"""玩家战绩快照的本地读写。"""

import json
from pathlib import Path
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from gsuid_core.pool import to_thread

from ..utils.paths import PLAYER_DATA_DIR
from ..api.dakanu.models.clan import DakanuClan
from ..api.dakanu.models.player import DakanuLeisure, DakanuProfile


class _SnapshotRecord(BaseModel):
    profile: DakanuProfile
    leisure: DakanuLeisure | None
    clan: DakanuClan | None
    saved_at: int


PLAYER_DATA_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class PlayerSnapshot:
    profile: DakanuProfile
    leisure: DakanuLeisure | None
    clan: DakanuClan | None
    saved_at: int


def player_data_path(player_id: str) -> Path:
    if not player_id.isdigit():
        raise ValueError("player_id must be numeric")
    return PLAYER_DATA_DIR / f"{player_id}.json"


def has_player_data(player_id: str) -> bool:
    path = player_data_path(player_id)
    return path.is_file() and path.stat().st_size > 0


def _write_snapshot_sync(snapshot: PlayerSnapshot) -> None:
    target = player_data_path(snapshot.profile.player.id)
    record = _SnapshotRecord(
        profile=snapshot.profile,
        leisure=snapshot.leisure,
        clan=snapshot.clan,
        saved_at=snapshot.saved_at,
    )
    temp = target.with_suffix(".json.tmp")
    payload = record.model_dump(mode="json", by_alias=True)
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temp.replace(target)


async def save_player_snapshot(snapshot: PlayerSnapshot) -> Path:
    """原子写入快照；中断时不会留下半个 JSON。"""
    await to_thread(_write_snapshot_sync)(snapshot)
    return player_data_path(snapshot.profile.player.id)


def _read_snapshot_sync(player_id: str) -> PlayerSnapshot | None:
    path = player_data_path(player_id)
    if not path.is_file():
        return None
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    try:
        record = _SnapshotRecord.model_validate(raw)
    except ValidationError:
        return None
    return PlayerSnapshot(
        profile=record.profile,
        leisure=record.leisure,
        clan=record.clan,
        saved_at=record.saved_at,
    )


async def load_player_snapshot(player_id: str) -> PlayerSnapshot | None:
    return await to_thread(_read_snapshot_sync)(player_id)
