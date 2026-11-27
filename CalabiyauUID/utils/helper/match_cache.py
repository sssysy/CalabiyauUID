"""对局详情（阵容）与回放统计的内存 LRU + 本地磁盘两级缓存。"""

import re
import json
import time
from pathlib import Path

from gsuid_core.pool import to_thread
from gsuid_core.logger import logger

from ..utils.cache import AsyncTtlCache, touch_cache_mtime
from ..utils.paths import MATCH_STATS_CACHE_DIR, MATCH_DETAIL_CACHE_DIR
from ..api.dakanu.requests import fetch_match_detail, fetch_match_statistics_payload
from ..api.dakanu.models.match import DakanuMatchTeam, DakanuMatchDetail, DakanuMatchPlayer, is_valid_room_id
from ..api.dakanu.models.match_stats import (
    DakanuMatchStatistics,
    parse_match_statistics,
)

_DETAIL_MEMORY_MAXSIZE = 256
_STATS_MEMORY_MAXSIZE = 64

_RANK_BOMB_RE = re.compile(r"(?:^|[_\s])RANK_BOMB(?:$|[_\s])", re.IGNORECASE)
_CAMP_ID_RE = re.compile(r"^RoomCamp_CAMP_\d+$")
_REGION_RE = re.compile(r"^[a-z0-9_-]{1,16}$")


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


def _is_rank_bomb_mode(detail: DakanuMatchDetail, match_mode: str | None) -> bool:
    mode_text = match_mode
    if not mode_text and detail.matchMode:
        mode_text = detail.matchMode
    return bool(mode_text and _RANK_BOMB_RE.search(mode_text))


def _has_complete_rank_bomb_teams(teams: list[DakanuMatchTeam]) -> bool:
    camp_counts: dict[str, int] = {}
    seen_players: set[str] = set()
    for team in teams:
        camp_id = team.id.strip()
        if not _CAMP_ID_RE.fullmatch(camp_id):
            return False
        for player in team.players:
            player_id = player.playerId
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
    if detail.ok is not True:
        return False
    if detail.roomId != room_id:
        return False
    if detail.hasDetail is not True:
        return False
    if not detail.teams:
        return False
    if _is_rank_bomb_mode(detail, match_mode) and not _has_complete_rank_bomb_teams(detail.teams):
        return False
    return True


def _retarget_match_detail(detail: DakanuMatchDetail, player_id: str | None) -> DakanuMatchDetail:
    """按当前查看视角重算 isTarget，保证同一 roomId 跨玩家复用不串号。"""
    teams = detail.teams
    retargeted_teams: list[DakanuMatchTeam] = []
    for team in teams:
        players: list[DakanuMatchPlayer] = [
            player.model_copy(update={"isTarget": bool(player_id and player.playerId == player_id)})
            for player in team.players
        ]
        retargeted_teams.append(team.model_copy(update={"players": players}))
    return detail.model_copy(update={"teams": retargeted_teams, "viewerPlayerId": player_id})


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _atomic_write_text(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f"{target.name}.{time.monotonic_ns()}.tmp")
    try:
        temp.write_text(content, encoding="utf-8")
        temp.replace(target)
    except OSError as exc:
        logger.warning(f"[卡拉彼丘·对局缓存] 写入缓存文件 {target.name} 失败：{exc}")
        _safe_unlink(temp)
        return


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
    if not isinstance(detail_obj, dict):
        _safe_unlink(path)
        return None
    try:
        detail = DakanuMatchDetail.model_validate(detail_obj)
    except ValueError:
        _safe_unlink(path)
        return None
    if not _is_cacheable_match_detail(detail, room_id, match_mode):
        _safe_unlink(path)
        return None
    touch_cache_mtime(path)
    return detail


def _write_detail_to_disk_sync(room_id: str, detail: DakanuMatchDetail) -> None:
    path = match_detail_cache_path(room_id)
    record = {"saved_at": int(time.time()), "detail": detail.model_dump(mode="json", by_alias=True)}
    serialized = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    _atomic_write_text(path, serialized)


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
    touch_cache_mtime(path)
    return parsed


def _write_stats_to_disk_sync(room_id: str, region: str, raw_json: str) -> None:
    path = match_stats_cache_path(room_id, region)
    _atomic_write_text(path, raw_json)


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
