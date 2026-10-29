"""玩家战绩快照的本地读写。"""

import json
from typing import TypedDict
from pathlib import Path
from dataclasses import dataclass

from gsuid_core.pool import to_thread
from gsuid_core.data_store import get_res_path

from ..api.dakanu import DakanuClan, DakanuLeisure, DakanuProfile


class DakanuSnapshotPayload(TypedDict):
    profile: DakanuProfile
    leisure: DakanuLeisure | None
    clan: DakanuClan | None
    saved_at: int


class DakanuSnapshotRaw(TypedDict):
    profile: object
    leisure: object
    clan: object
    saved_at: object


PLAYER_DATA_DIR: Path = get_res_path(["CalabiyauUID", "player_data"])


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
    target = player_data_path(snapshot.profile["player"]["id"])
    payload: DakanuSnapshotPayload = {
        "profile": snapshot.profile,
        "leisure": snapshot.leisure,
        "clan": snapshot.clan,
        "saved_at": snapshot.saved_at,
    }
    temp = target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temp.replace(target)


async def save_player_snapshot(snapshot: PlayerSnapshot) -> Path:
    """原子写入快照；中断时不会留下半个 JSON。"""
    await to_thread(_write_snapshot_sync)(snapshot)
    return player_data_path(snapshot.profile["player"]["id"])


def _read_snapshot_sync(player_id: str) -> PlayerSnapshot | None:
    path = player_data_path(player_id)
    if not path.is_file():
        return None
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    payload: DakanuSnapshotRaw = raw
    profile = payload["profile"]
    leisure = payload["leisure"]
    clan = payload["clan"]
    saved_at = payload["saved_at"]
    if not isinstance(profile, dict):
        return None
    if not isinstance(leisure, dict) and leisure is not None:
        return None
    if not isinstance(clan, dict) and clan is not None:
        return None
    if not isinstance(saved_at, int):
        return None
    typed_leisure: DakanuLeisure | None
    if isinstance(leisure, dict):
        typed_leisure = leisure
    else:
        typed_leisure = None
    typed_clan: DakanuClan | None
    if isinstance(clan, dict):
        typed_clan = clan
    else:
        typed_clan = None
    typed_profile: DakanuProfile = profile
    return PlayerSnapshot(
        profile=typed_profile,
        leisure=typed_leisure,
        clan=typed_clan,
        saved_at=saved_at,
    )


async def load_player_snapshot(player_id: str) -> PlayerSnapshot | None:
    return await to_thread(_read_snapshot_sync)(player_id)
