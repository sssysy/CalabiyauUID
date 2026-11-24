"""对局详情（阵容）与回放统计的内存 LRU + 本地磁盘两级缓存。"""

import os
import re
import json
import time
from typing import TypedDict
from pathlib import Path

from gsuid_core.pool import to_thread
from gsuid_core.logger import logger

from ..api.dakanu import (
    DakanuMatchTeam,
    DakanuMatchDetail,
    DakanuMatchPlayer,
    DakanuMatchStatistics,
    is_valid_room_id,
    fetch_match_detail,
    parse_match_statistics,
    is_match_detail_response,
    fetch_match_statistics_payload,
)
from ..utils.cache import AsyncTtlCache
from ..utils.paths import MATCH_STATS_CACHE_DIR, MATCH_DETAIL_CACHE_DIR

_DETAIL_MEMORY_MAXSIZE = 256
_DETAIL_DISK_MAX_FILES = 300
_STATS_MEMORY_MAXSIZE = 64
_STATS_DISK_MAX_FILES = 100

_RANK_BOMB_RE = re.compile(r"(?:^|[_\s])RANK_BOMB(?:$|[_\s])", re.IGNORECASE)
_CAMP_ID_RE = re.compile(r"^RoomCamp_CAMP_\d+$")
_REGION_RE = re.compile(r"^[a-z0-9_-]{1,16}$")


class _MatchDetailDiskRecord(TypedDict):
    saved_at: int
    detail: DakanuMatchDetail


_detail_cache: AsyncTtlCache[str, DakanuMatchDetail | None] = AsyncTtlCache(maxsize=_DETAIL_MEMORY_MAXSIZE)
_stats_cache: AsyncTtlCache[str, DakanuMatchStatistics] = AsyncTtlCache(maxsize=_STATS_MEMORY_MAXSIZE)


def _normalize_region(region: str) -> str:
    cleaned = region.strip().lower()
    if not _REGION_RE.fullmatch(cleaned):
        raise ValueError(f"invalid region: {region}")
    return cleaned


def match_detail_cache_path(room_id: str) -> Path:
    if not is_valid_room_id(room_id):
        raise ValueError("room_id must be a valid Dakanu room id")
    return MATCH_DETAIL_CACHE_DIR / f"{room_id}.json"


def match_stats_cache_path(room_id: str, region: str) -> Path:
    if not is_valid_room_id(room_id):
        raise ValueError("room_id must be a valid Dakanu room id")
    cleaned_region = _normalize_region(region)
    return MATCH_STATS_CACHE_DIR / f"{cleaned_region}_{room_id}.json"


def _is_valid_match_player(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    required_str = ("playerId", "nickname", "teamId", "teamLabel", "roleName", "result")
    required_int = ("avatarId", "roleId", "kills", "assists", "deaths", "damage", "score")
    required_bool = ("mvp", "svp", "isTarget")
    for key in required_str:
        if key not in value or not isinstance(value[key], str):
            return False
    for key in required_int:
        if key not in value or not isinstance(value[key], int) or isinstance(value[key], bool):
            return False
    for key in required_bool:
        if key not in value or not isinstance(value[key], bool):
            return False
    return True


def _is_valid_match_teams(teams: object) -> bool:
    if not isinstance(teams, list) or not teams:
        return False
    has_players = False
    for team in teams:
        if not isinstance(team, dict):
            return False
        if "id" not in team or not isinstance(team["id"], str):
            return False
        if "label" not in team or not isinstance(team["label"], str):
            return False
        if "players" not in team or not isinstance(team["players"], list):
            return False
        for player in team["players"]:
            if not _is_valid_match_player(player):
                return False
            has_players = True
    return has_players


def _is_rank_bomb_mode(detail: DakanuMatchDetail, match_mode: str | None) -> bool:
    mode_text = match_mode
    if not mode_text and "matchMode" in detail and isinstance(detail["matchMode"], str):
        mode_text = detail["matchMode"]
    return bool(mode_text and _RANK_BOMB_RE.search(mode_text))


def _has_complete_rank_bomb_teams(teams: list[DakanuMatchTeam]) -> bool:
    camp_counts: dict[str, int] = {}
    seen_players: set[str] = set()
    for team in teams:
        camp_id = team["id"].strip()
        if not _CAMP_ID_RE.fullmatch(camp_id):
            return False
        for player in team["players"]:
            player_id = player["playerId"]
            if not player_id or player_id in seen_players:
                return False
            seen_players.add(player_id)
            camp_counts[camp_id] = (camp_counts[camp_id] if camp_id in camp_counts else 0) + 1
    return camp_counts == {"RoomCamp_CAMP_1": 5, "RoomCamp_CAMP_2": 5}


def _is_cacheable_match_detail(
    detail: DakanuMatchDetail | None,
    room_id: str,
    match_mode: str | None = None,
) -> bool:
    if detail is None:
        return False
    if "ok" not in detail or detail["ok"] is not True:
        return False
    if "roomId" not in detail or detail["roomId"] != room_id:
        return False
    if "hasDetail" not in detail or detail["hasDetail"] is not True:
        return False
    if "teams" not in detail or "rounds" not in detail:
        return False
    if not _is_valid_match_teams(detail["teams"]):
        return False
    if _is_rank_bomb_mode(detail, match_mode) and not _has_complete_rank_bomb_teams(detail["teams"]):
        return False
    return True


def _retarget_match_detail(detail: DakanuMatchDetail, player_id: str | None) -> DakanuMatchDetail:
    """按当前查看视角重算 isTarget，保证同一 roomId 跨玩家复用不串号。"""
    teams = detail["teams"] if "teams" in detail else []
    retargeted_teams: list[DakanuMatchTeam] = []
    for team in teams:
        players: list[DakanuMatchPlayer] = [
            {**player, "isTarget": bool(player_id and player["playerId"] == player_id)} for player in team["players"]
        ]
        team_copy: DakanuMatchTeam = {
            "id": team["id"],
            "label": team["label"],
            "players": players,
        }
        if "side" in team:
            team_copy["side"] = team["side"]
        if "sideLabel" in team:
            team_copy["sideLabel"] = team["sideLabel"]
        retargeted_teams.append(team_copy)
    updated: DakanuMatchDetail = {**detail, "teams": retargeted_teams}
    if player_id is not None:
        updated["viewerPlayerId"] = player_id
    else:
        updated["viewerPlayerId"] = None
    return updated


def _touch_mtime(path: Path) -> None:
    try:
        os.utime(path, None)
    except OSError:
        pass


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _prune_disk_dir(directory: Path, max_files: int) -> None:
    if not directory.is_dir():
        return
    entries: list[tuple[float, Path]] = []
    try:
        for item in directory.iterdir():
            if not item.is_file() or item.suffix != ".json":
                continue
            try:
                entries.append((item.stat().st_mtime, item))
            except OSError:
                continue
    except OSError:
        return
    excess = len(entries) - max_files
    if excess <= 0:
        return
    entries.sort(key=lambda pair: pair[0])
    for _, stale_path in entries[:excess]:
        _safe_unlink(stale_path)


def _atomic_write_text(target: Path, content: str, max_files: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f"{target.name}.{time.monotonic_ns()}.tmp")
    try:
        temp.write_text(content, encoding="utf-8")
        temp.replace(target)
    except OSError as exc:
        logger.warning(f"[卡拉彼丘·对局缓存] 写入缓存文件 {target.name} 失败：{exc}")
        _safe_unlink(temp)
        return
    _prune_disk_dir(target.parent, max_files)


def _read_detail_from_disk_sync(room_id: str, match_mode: str | None) -> DakanuMatchDetail | None:
    path = match_detail_cache_path(room_id)
    if not path.is_file():
        return None
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(f"[卡拉彼丘·对局缓存] 读取对局详情缓存 {room_id} 失败，已清理：{exc}")
        _safe_unlink(path)
        return None
    if not isinstance(raw, dict) or "detail" not in raw:
        _safe_unlink(path)
        return None
    detail_obj = raw["detail"]
    if not is_match_detail_response(detail_obj) or not _is_cacheable_match_detail(detail_obj, room_id, match_mode):
        _safe_unlink(path)
        return None
    _touch_mtime(path)
    return detail_obj


def _write_detail_to_disk_sync(room_id: str, detail: DakanuMatchDetail) -> None:
    path = match_detail_cache_path(room_id)
    record: _MatchDetailDiskRecord = {
        "saved_at": int(time.time()),
        "detail": detail,
    }
    serialized = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    _atomic_write_text(path, serialized, _DETAIL_DISK_MAX_FILES)


def _read_stats_from_disk_sync(room_id: str, region: str) -> DakanuMatchStatistics | None:
    path = match_stats_cache_path(room_id, region)
    if not path.is_file():
        return None
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(f"[卡拉彼丘·对局缓存] 读取对局统计缓存 {room_id} 失败，已清理：{exc}")
        _safe_unlink(path)
        return None
    parsed = parse_match_statistics(raw)
    if parsed is None or parsed.room_id != room_id:
        _safe_unlink(path)
        return None
    _touch_mtime(path)
    return parsed


def _write_stats_to_disk_sync(room_id: str, region: str, raw_json: str) -> None:
    path = match_stats_cache_path(room_id, region)
    _atomic_write_text(path, raw_json, _STATS_DISK_MAX_FILES)


async def get_match_detail(
    player_id: str | None,
    room_id: str,
    *,
    match_mode: str | None = None,
    use_cache: bool = True,
) -> DakanuMatchDetail | None:
    """获取单场对局详情；优先命中内存 LRU 与磁盘缓存，并按视角重算 isTarget。"""
    cleaned_room = room_id.strip()
    if not is_valid_room_id(cleaned_room):
        return None

    async def _load() -> DakanuMatchDetail | None:
        if use_cache:
            disk_cached = await to_thread(_read_detail_from_disk_sync)(cleaned_room, match_mode)
            if disk_cached is not None:
                return disk_cached
        fetched = await fetch_match_detail(player_id, cleaned_room)
        if _is_cacheable_match_detail(fetched, cleaned_room, match_mode) and fetched is not None:
            neutral = _retarget_match_detail(fetched, None)
            await to_thread(_write_detail_to_disk_sync)(cleaned_room, neutral)
            return neutral
        return fetched

    cached = await _detail_cache.get_or_load(
        cleaned_room,
        _load,
        should_cache=lambda value: _is_cacheable_match_detail(value, cleaned_room, match_mode),
        use_cache=use_cache,
    )
    if cached is None:
        return None
    return _retarget_match_detail(cached, player_id)


async def get_match_statistics(
    room_id: str,
    *,
    region: str = "cn",
    use_cache: bool = True,
) -> DakanuMatchStatistics:
    """获取单场对局回放统计；优先命中内存 LRU 与磁盘缓存。"""
    cleaned_room = room_id.strip()
    cleaned_region = _normalize_region(region)
    cache_key = f"{cleaned_region}:{cleaned_room}"

    async def _load() -> DakanuMatchStatistics:
        if use_cache and is_valid_room_id(cleaned_room):
            disk_cached = await to_thread(_read_stats_from_disk_sync)(cleaned_room, cleaned_region)
            if disk_cached is not None:
                return disk_cached
        payload = await fetch_match_statistics_payload(cleaned_room, region=cleaned_region)
        if is_valid_room_id(cleaned_room):
            await to_thread(_write_stats_to_disk_sync)(cleaned_room, cleaned_region, payload.raw_json)
        return payload.stats

    return await _stats_cache.get_or_load(cache_key, _load, use_cache=use_cache)
