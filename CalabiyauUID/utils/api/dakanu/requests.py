"""Dakanu 全异步 API 请求层（NTEUID 风格：薄请求 + Pydantic 出口校验）。"""

from __future__ import annotations

import json
import asyncio
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import httpx
from pydantic import ValidationError

from gsuid_core.logger import logger

from .client import (
    BASE_URL,
    DakanuError,
    parse_model,
    request_raw,
    request_json,
    safe_error_text,
    format_rate_limit_message,
)
from .models.base import parse_tolerant_list
from .models.clan import DakanuClan, DakanuClanMembersResponse
from .models.match import DakanuMatchDetail, DakanuReplayTicket, is_valid_room_id
from ...utils.cache import AsyncTtlCache
from .models.banned import DakanuBannedResponse
from .models.player import (
    DakanuLeisure,
    DakanuProfile,
    DakanuRefreshJob,
    DakanuPlayerSeason,
    DakanuPlayerSuggestion,
)
from .models.ranking import (
    DakanuRankingFloor,
    DakanuCurrentSeason,
    DakanuRankingsBoard,
    DakanuRankingSeasons,
    DakanuRolesRankingBoard,
)
from .models.community import DakanuGameActivity, DakanuChatAggregate
from .models.match_stats import (
    DakanuMatchStatistics,
    DakanuMatchStatisticsPayload,
    parse_match_statistics,
)

_REFRESH_POLL_INTERVAL = 1.5
_REFRESH_TIMEOUT = 90.0
_CLAN_MEMBERS_POLL_INTERVAL = 1.5
_CLAN_MEMBERS_MAX_POLLS = 6
_META_CACHE_TTL_SECONDS = 300.0
_GAME_ACTIVITY_RANGES = frozenset({"6h", "24h", "7d", "30d"})

_meta_roles_cache: AsyncTtlCache[str, dict[int, str]] = AsyncTtlCache(
    maxsize=1,
    ttl_seconds=_META_CACHE_TTL_SECONDS,
)
_ranking_seasons_cache: AsyncTtlCache[str, DakanuRankingSeasons] = AsyncTtlCache(
    maxsize=1,
    ttl_seconds=_META_CACHE_TTL_SECONDS,
)


def _require_ok_dict(payload: Any, *, log_tag: str, label: str, error_msg: str | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        logger.warning(f"{log_tag} {label}响应结构异常")
        raise DakanuError(error_msg or f"{label}数据格式异常，请稍后再试。")
    return payload


async def fetch_profile(player_id: str) -> DakanuProfile:
    """读取玩家缓存档案；不在查询链路里触发上游刷新。"""
    payload = await request_json(
        "GET",
        f"/api/summoner/{quote(player_id, safe='')}/cache",
        log_tag="[卡拉彼丘·战绩总览]",
        label="战绩",
        status_messages={
            204: "没有找到这个玩家的战绩缓存。",
            404: "没有找到这个玩家的战绩缓存。",
        },
        upstream_error_msg="战绩站暂时无法读取数据，请稍后再试。",
        fallback_error_msg="读取战绩失败，请稍后再试。",
    )
    data = _require_ok_dict(payload, log_tag="[卡拉彼丘·战绩总览]", label="战绩")
    return parse_model(DakanuProfile, data.get("profile"), log_tag="[卡拉彼丘·战绩总览]", label="战绩")


async def fetch_match_detail(player_id: str | None, room_id: str) -> DakanuMatchDetail | None:
    """读取单场对局详情；无详情或非致命异常时返回 None。"""
    params: dict[str, str] = {"player": player_id} if player_id else {}
    try:
        response = await request_raw(
            "GET",
            f"/api/match-detail/{quote(room_id, safe='')}",
            params=params,
            headers={"X-Karabi-Region": "cn"},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        logger.warning(f"[卡拉彼丘·最近对局] 读取对局 {room_id} 详情失败：{exc}")
        return None
    if response.status_code == 404:
        return None
    if response.status_code == 429:
        raise DakanuError(format_rate_limit_message(response, prefix="对局详情查询过于频繁"))
    if response.status_code in {502, 503, 504}:
        raise DakanuError("战绩站暂时无法读取对局详情，请稍后再试。")
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·最近对局] 读取对局 {room_id} 返回 HTTP {response.status_code}")
        return None
    try:
        payload: Any = response.json()
    except ValueError:
        logger.warning(f"[卡拉彼丘·最近对局] 对局 {room_id} 返回非 JSON 响应")
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("ok") is not True
        or not isinstance(payload.get("teams"), list)
        or not isinstance(payload.get("rounds"), list)
    ):
        logger.warning(f"[卡拉彼丘·最近对局] 对局 {room_id} 响应结构异常")
        return None
    try:
        return DakanuMatchDetail.model_validate(payload)
    except ValidationError:
        logger.warning(f"[卡拉彼丘·最近对局] 对局 {room_id} 响应结构异常")
        return None


def _resolve_replay_download_url(raw_url: str, room_id: str) -> str | None:
    base_parts = urlsplit(BASE_URL)
    resolved = urljoin(f"{BASE_URL}/", raw_url)
    parts = urlsplit(resolved)
    if parts.scheme != base_parts.scheme or parts.netloc != base_parts.netloc:
        return None
    if parts.path != f"/api/match/{room_id}/replay/download":
        return None
    return resolved


async def fetch_replay_download_ticket(room_id: str) -> DakanuReplayTicket:
    """申请对局回放下载凭证与临时 Cookie（独立短生命周期客户端隔离 Cookie）。"""
    cleaned = room_id.strip()
    if not is_valid_room_id(cleaned):
        raise DakanuError("对局 ID 格式不正确，请传入纯数字对局 ID。")
    try:
        response = await request_raw(
            "POST",
            f"/api/match/{cleaned}/replay",
            timeout=30.0,
            ephemeral=True,
        )
    except httpx.HTTPError as exc:
        logger.warning(f"[卡拉彼丘·回放下载] 请求对局 {cleaned} 回放地址失败：{exc}")
        raise DakanuError("请求对局回放地址失败，请稍后再试。") from None

    if response.status_code == 404:
        raise DakanuError(f"没有找到对局 {cleaned} 的回放文件。")
    if response.status_code == 429:
        raise DakanuError(format_rate_limit_message(response, prefix="回放请求过于频繁"))
    if response.status_code in {502, 503, 504}:
        raise DakanuError("战绩站暂时无法获取回放，请稍后再试。")
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·回放下载] 对局 {cleaned} 返回 HTTP {response.status_code}")
        raise DakanuError(safe_error_text(response) or "获取对局回放地址失败，请稍后再试。")

    try:
        payload: Any = response.json()
    except ValueError:
        logger.warning(f"[卡拉彼丘·回放下载] 对局 {cleaned} 返回非 JSON 响应")
        raise DakanuError("回放响应数据格式异常，请稍后再试。") from None
    if not isinstance(payload, dict):
        raise DakanuError("回放响应数据格式异常，请稍后再试。")
    if payload.get("ok") is not True:
        err = payload.get("error")
        if isinstance(err, str) and err.strip() and "<" not in err:
            raise DakanuError(err.strip())
        raise DakanuError("战绩站暂未提供该对局的回放文件。")

    raw_url = payload.get("url")
    if not isinstance(raw_url, str):
        raise DakanuError("未获取到可用的回放下载地址。")
    resolved_url = _resolve_replay_download_url(raw_url, cleaned)
    if resolved_url is None:
        logger.warning(f"[卡拉彼丘·回放下载] 对局 {cleaned} 返回异常下载地址：{raw_url}")
        raise DakanuError("回放下载地址无效，请稍后再试。")

    return DakanuReplayTicket(
        room_id=cleaned,
        download_url=resolved_url,
        cookies={str(name): str(value) for name, value in response.cookies.items()},
        verified=bool(payload.get("verified")) if isinstance(payload.get("verified"), bool) else False,
    )


async def start_profile_refresh(player_id: str) -> DakanuRefreshJob:
    """触发玩家档案刷新任务。"""
    payload = await request_json(
        "POST",
        f"/api/summoner/{quote(player_id, safe='')}/refresh",
        log_tag="[卡拉彼丘·刷新数据]",
        label="战绩刷新",
        ok_statuses=frozenset({200, 202}),
        status_messages={404: "没有找到该玩家的战绩数据。"},
        upstream_error_msg="战绩站暂时无法查询，请稍后再试。",
        fallback_error_msg="刷新战绩失败，请稍后再试。",
        invalid_json_msg="战绩数据格式异常，请稍后再试。",
    )
    data = _require_ok_dict(
        payload, log_tag="[卡拉彼丘·刷新数据]", label="战绩", error_msg="战绩数据格式异常，请稍后再试。"
    )
    return parse_model(DakanuRefreshJob, data.get("job"), log_tag="[卡拉彼丘·刷新数据]", label="战绩")


async def fetch_refresh_status(player_id: str) -> DakanuRefreshJob:
    """查询玩家档案刷新任务状态。"""
    payload = await request_json(
        "GET",
        f"/api/summoner/{quote(player_id, safe='')}/refresh",
        log_tag="[卡拉彼丘·刷新数据]",
        label="刷新状态",
        status_messages={404: "刷新任务不存在或已过期。"},
        upstream_error_msg="战绩站暂时无法查询，请稍后再试。",
        fallback_error_msg="查询刷新状态失败，请稍后再试。",
        invalid_json_msg="战绩数据格式异常，请稍后再试。",
    )
    data = _require_ok_dict(
        payload, log_tag="[卡拉彼丘·刷新数据]", label="战绩", error_msg="战绩数据格式异常，请稍后再试。"
    )
    return parse_model(DakanuRefreshJob, data.get("job"), log_tag="[卡拉彼丘·刷新数据]", label="战绩")


async def refresh_profile(player_id: str) -> DakanuProfile:
    """启动刷新并轮询至缓存可读；超时或失败时抛出 DakanuError。"""
    restarted = False
    try:
        job = await start_profile_refresh(player_id)
    except DakanuError as start_exc:
        try:
            job = await fetch_refresh_status(player_id)
        except DakanuError:
            raise start_exc from None

    deadline = asyncio.get_running_loop().time() + _REFRESH_TIMEOUT
    while job.state == "running":
        if asyncio.get_running_loop().time() >= deadline:
            raise DakanuError("刷新仍在进行，请稍后用 kq战绩总览 查看。")
        await asyncio.sleep(_REFRESH_POLL_INTERVAL)
        try:
            job = await fetch_refresh_status(player_id)
        except DakanuError as poll_exc:
            if restarted or str(poll_exc) != "刷新任务不存在或已过期。":
                raise
            restarted = True
            job = await start_profile_refresh(player_id)
    if job.state == "failed":
        message = job.error.message.strip() if job.error is not None else ""
        raise DakanuError(message or "战绩刷新失败，请稍后再试。")

    for _ in range(5):
        try:
            return await fetch_profile(player_id)
        except DakanuError as exc:
            if str(exc) != "没有找到这个玩家的战绩缓存。":
                raise
        await asyncio.sleep(_REFRESH_POLL_INTERVAL)
    raise DakanuError("刷新已完成，但暂时没有读到玩家缓存。")


async def fetch_clan(clan_id: str) -> DakanuClan | None:
    """按 clanId 读取战队信息；读取失败时不打断总览。"""
    if not clan_id:
        return None
    try:
        response = await request_raw("GET", "/api/clans/search", params={"clan_id": clan_id, "limit": 1}, timeout=20.0)
    except httpx.HTTPError as exc:
        logger.warning(f"[卡拉彼丘·战绩总览] 读取战队 {clan_id} 失败：{exc}")
        return None
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·战绩总览] 读取战队 {clan_id} 返回 HTTP {response.status_code}")
        return None
    try:
        payload: Any = response.json()
    except ValueError:
        logger.warning(f"[卡拉彼丘·战绩总览] 战队 {clan_id} 返回非 JSON 响应")
        return None
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return None
    for clan in parse_tolerant_list(DakanuClan, payload.get("clans")):
        if clan.clanId == clan_id:
            return clan
    return None


async def fetch_leisure(player_id: str) -> DakanuLeisure | None:
    """读取挑战赛数据；接口无数据或失败时返回 None。"""
    try:
        response = await request_raw(
            "GET",
            f"/api/summoner/{quote(player_id, safe='')}/leisure",
            params={"season_id": 0},
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        logger.warning(f"[卡拉彼丘·战绩总览] 读取玩家 {player_id} 挑战赛数据失败：{exc}")
        return None
    if response.status_code == 204:
        return None
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·战绩总览] 读取玩家 {player_id} 挑战赛数据返回 HTTP {response.status_code}")
        return None
    try:
        payload: Any = response.json()
    except ValueError:
        logger.warning(f"[卡拉彼丘·战绩总览] 玩家 {player_id} 挑战赛数据不是 JSON")
        return None
    if not isinstance(payload, dict) or payload.get("ok") is not True or not isinstance(payload.get("leisure"), dict):
        return None
    try:
        return DakanuLeisure.model_validate(payload["leisure"])
    except ValidationError:
        return None


async def fetch_rankings(
    rank_type: int = 1,
    page: int = 1,
    page_size: int = 50,
    *,
    sub_type: int | None = None,
    season_id: int = 0,
) -> DakanuRankingsBoard:
    """读取 Dakanu 在线排行榜数据。"""
    params: dict[str, int] = {"type": rank_type, "page": page, "page_size": page_size}
    if sub_type is not None:
        params["sub_type"] = sub_type
    if season_id > 0:
        params["season_id"] = season_id
    payload = await request_json(
        "GET",
        "/api/rankings",
        params=params,
        log_tag="[卡拉彼丘·排位排行]",
        label="榜单",
        upstream_error_msg="战绩站暂时无法读取榜单数据，请稍后再试。",
    )
    return parse_model(DakanuRankingsBoard, payload, log_tag="[卡拉彼丘·排位排行]", label="榜单")


async def fetch_ranking_floor(season_id: int = 0) -> DakanuRankingFloor | None:
    """读取当前奇点底分；接口异常时返回 None，不阻断榜单渲染。"""
    try:
        response = await request_raw("GET", "/api/rankings/floor", params={"season_id": season_id}, timeout=20.0)
    except httpx.HTTPError as exc:
        logger.warning(f"[卡拉彼丘·排位排行] 请求奇点底分失败：{exc}")
        return None
    if response.status_code == 204:
        return None
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·排位排行] 读取奇点底分返回 HTTP {response.status_code}")
        return None
    try:
        payload: Any = response.json()
    except ValueError:
        logger.warning("[卡拉彼丘·排位排行] 奇点底分返回非 JSON 响应")
        return None
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return None
    try:
        return DakanuRankingFloor.model_validate(payload)
    except ValidationError:
        return None


async def fetch_current_season() -> DakanuCurrentSeason | None:
    """读取当前排位赛季信息；接口异常时返回 None。"""
    try:
        response = await request_raw("GET", "/api/seasons/current", timeout=20.0)
    except httpx.HTTPError as exc:
        logger.warning(f"[卡拉彼丘·排位排行] 请求当前赛季失败：{exc}")
        return None
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·排位排行] 读取当前赛季返回 HTTP {response.status_code}")
        return None
    try:
        payload: Any = response.json()
    except ValueError:
        logger.warning("[卡拉彼丘·排位排行] 当前赛季返回非 JSON 响应")
        return None
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return None
    try:
        return DakanuCurrentSeason.model_validate(payload)
    except ValidationError:
        return None


async def _load_ranking_seasons() -> DakanuRankingSeasons:
    payload = await request_json(
        "GET",
        "/api/rankings/seasons",
        timeout=20.0,
        log_tag="[卡拉彼丘·赛季查询]",
        label="赛季列表",
        invalid_json_msg="赛季列表格式异常，请稍后再试。",
        network_error_msg="读取赛季列表失败，请稍后再试。",
    )
    return parse_model(
        DakanuRankingSeasons,
        payload,
        log_tag="[卡拉彼丘·赛季查询]",
        label="赛季列表",
        error_msg="赛季列表格式异常，请稍后再试。",
    )


async def fetch_ranking_seasons() -> DakanuRankingSeasons:
    """读取 Dakanu `/api/rankings/seasons` 赛季目录，带 5 分钟内存缓存。"""
    return await _ranking_seasons_cache.get_or_load("default", _load_ranking_seasons)


async def fetch_player_season(player_id: str, season_id: int) -> DakanuPlayerSeason | None:
    """按需读取玩家指定历史赛季战绩，无数据时返回 None。"""
    payload = await request_json(
        "GET",
        f"/api/summoner/{quote(player_id, safe='')}/seasons",
        params={"season_id": season_id},
        timeout=20.0,
        log_tag="[卡拉彼丘·战绩总览]",
        label="赛季战绩",
        empty_statuses=frozenset({204, 404}),
        status_messages={
            401: "该玩家已开启隐私保护，无法查看该赛季战绩。",
            403: "该玩家已开启隐私保护，无法查看该赛季战绩。",
            409: "战绩站上游会话暂不可用，请稍后再试。",
        },
        upstream_error_msg="战绩站暂时无法读取该赛季数据，请稍后再试。",
        network_error_msg="读取赛季战绩失败，请稍后再试。",
    )
    if payload is None:
        return None
    data = _require_ok_dict(payload, log_tag="[卡拉彼丘·战绩总览]", label="赛季战绩")
    return parse_model(DakanuPlayerSeason, data.get("season"), log_tag="[卡拉彼丘·战绩总览]", label="赛季战绩")


async def fetch_roles_ranking(*, ranked_only: bool = True, min_games: int = 3) -> DakanuRolesRankingBoard:
    """读取 Dakanu 超弦体胜率与登场率排行榜。"""
    params: dict[str, int] = {"min_games": min_games}
    if not ranked_only:
        params["all"] = 1
    payload = await request_json(
        "GET",
        "/api/roles/ranking",
        params=params,
        log_tag="[卡拉彼丘·超弦体排行]",
        label="超弦体排行",
    )
    return parse_model(DakanuRolesRankingBoard, payload, log_tag="[卡拉彼丘·超弦体排行]", label="超弦体排行")


async def _load_meta_roles() -> dict[int, str]:
    payload = await request_json(
        "GET",
        "/api/meta",
        timeout=20.0,
        log_tag="[卡拉彼丘·角色字典]",
        label="角色列表",
        invalid_json_msg="角色列表格式异常，请稍后再试。",
        network_error_msg="读取角色列表失败，请稍后再试。",
    )
    data = _require_ok_dict(
        payload, log_tag="[卡拉彼丘·角色字典]", label="角色列表", error_msg="角色列表格式异常，请稍后再试。"
    )
    raw_roles = data.get("roles")
    if not isinstance(raw_roles, dict):
        raise DakanuError("角色列表格式异常，请稍后再试。")
    roles: dict[int, str] = {}
    for key, value in raw_roles.items():
        if isinstance(key, str) and key.isdigit() and isinstance(value, str) and value.strip():
            role_id = int(key)
            if role_id != 220:
                roles[role_id] = value.strip()
    return roles


async def fetch_meta_roles() -> dict[int, str]:
    """读取 Dakanu 角色 ID 到中文名映射，带 5 分钟内存缓存。"""
    roles = await _meta_roles_cache.get_or_load("default", _load_meta_roles)
    return dict(roles)


async def search_players(query: str) -> list[DakanuPlayerSuggestion]:
    """按昵称或 UID 搜索 Dakanu 玩家候选。"""
    cleaned = query.strip()
    if not cleaned:
        return []
    payload = await request_json(
        "GET",
        "/api/search/players",
        params={"q": cleaned},
        timeout=20.0,
        log_tag="[卡拉彼丘·玩家搜索]",
        label="玩家搜索结果",
        upstream_error_msg="战绩站暂时无法搜索玩家，请稍后再试。",
        fallback_error_msg="搜索玩家失败，请稍后再试。",
        network_error_msg="搜索玩家失败，请稍后再试。",
        invalid_json_msg="玩家搜索结果格式异常，请稍后再试。",
    )
    data = _require_ok_dict(
        payload,
        log_tag="[卡拉彼丘·玩家搜索]",
        label="玩家搜索结果",
        error_msg="玩家搜索结果格式异常，请稍后再试。",
    )
    raw_suggestions = data.get("suggestions")
    if not isinstance(raw_suggestions, list):
        raise DakanuError("玩家搜索结果格式异常，请稍后再试。")
    return parse_tolerant_list(DakanuPlayerSuggestion, raw_suggestions)


async def fetch_game_activity(range_key: str = "24h") -> DakanuGameActivity:
    """读取 Dakanu 玩家活跃趋势数据。"""
    if range_key not in _GAME_ACTIVITY_RANGES:
        raise ValueError(f"不支持的活跃范围：{range_key}")
    payload = await request_json(
        "GET",
        "/api/activity/game",
        params={"range": range_key},
        log_tag="[卡拉彼丘·活跃趋势]",
        label="玩家活跃趋势",
    )
    return parse_model(DakanuGameActivity, payload, log_tag="[卡拉彼丘·活跃趋势]", label="玩家活跃趋势")


async def fetch_chat_aggregate(limit_per_channel: int = 30) -> DakanuChatAggregate:
    """读取 Dakanu 世界频道聚合消息。"""
    payload = await request_json(
        "GET",
        "/api/chat/messages/aggregate",
        params={"limit_per_channel": limit_per_channel},
        log_tag="[卡拉彼丘·世界聊天]",
        label="世界频道动态",
    )
    return parse_model(DakanuChatAggregate, payload, log_tag="[卡拉彼丘·世界聊天]", label="世界频道动态")


async def search_clans(
    *,
    name: str | None = None,
    clan_id: str | None = None,
    limit: int = 10,
) -> list[DakanuClan]:
    """按战队名称或 ID 搜索 Dakanu 战队。"""
    params: dict[str, str] = {"limit": str(limit)}
    if clan_id is not None and clan_id.strip():
        params["clan_id"] = clan_id.strip()
    elif name is not None and name.strip():
        params["name"] = name.strip()
    else:
        raise DakanuError("请提供战队名称或战队 ID。")
    payload = await request_json(
        "GET",
        "/api/clans/search",
        params=params,
        log_tag="[卡拉彼丘·战队查询]",
        label="战队信息",
    )
    data = _require_ok_dict(payload, log_tag="[卡拉彼丘·战队查询]", label="战队")
    raw_clans = data.get("clans")
    if not isinstance(raw_clans, list):
        raise DakanuError("战队数据格式异常，请稍后再试。")
    return parse_tolerant_list(DakanuClan, raw_clans)


async def _fetch_clan_members_once(clan_id: str, refresh: bool) -> DakanuClanMembersResponse:
    params: dict[str, str] = {"refresh": "true"} if refresh else {}
    payload = await request_json(
        "GET",
        f"/api/clans/{quote(clan_id, safe='')}/members",
        params=params,
        log_tag="[卡拉彼丘·战队查询]",
        label="战队成员",
        ok_statuses=frozenset({200, 202}),
    )
    result = parse_model(DakanuClanMembersResponse, payload, log_tag="[卡拉彼丘·战队查询]", label="战队成员")
    if isinstance(payload, dict) and payload.get("refreshError") and not result.members:
        raise DakanuError("战队成员暂时无法读取，请稍后再试。")
    return result


async def fetch_clan_members(clan_id: str, *, refresh: bool = False) -> DakanuClanMembersResponse:
    """读取战队成员名册；若上游正在刷新则短轮询等待结果。"""
    result = await _fetch_clan_members_once(clan_id, refresh)
    if not result.refreshing or result.members:
        return result
    for _ in range(_CLAN_MEMBERS_MAX_POLLS):
        await asyncio.sleep(_CLAN_MEMBERS_POLL_INTERVAL)
        result = await _fetch_clan_members_once(clan_id, False)
        if not result.refreshing or result.members:
            return result
    if result.members:
        return result
    raise DakanuError("正在同步战队成员名册，请稍后重试。")


async def fetch_banned_players(
    *,
    offset: int = 0,
    limit: int = 21,
    query: str = "",
) -> DakanuBannedResponse:
    """拉取封神榜列表或按昵称/UID 搜索封禁记录。"""
    params: dict[str, str] = {"offset": str(max(0, offset)), "limit": str(max(1, limit))}
    cleaned = query.strip()
    if cleaned:
        params["q"] = cleaned
    payload = await request_json(
        "GET",
        "/api/banned-players",
        params=params,
        log_tag="[卡拉彼丘·封神榜]",
        label="封神榜",
    )
    return parse_model(DakanuBannedResponse, payload, log_tag="[卡拉彼丘·封神榜]", label="封神榜")


async def fetch_match_statistics_payload(room_id: str, *, region: str = "cn") -> DakanuMatchStatisticsPayload:
    """获取单场对局的回放解析统计数据及原始 JSON 文本。"""
    try:
        response = await request_raw(
            "GET",
            f"/api/match/{quote(room_id, safe='')}/statistics",
            params={"region": region, "view": "web"},
            headers={"X-Karabi-Region": region},
            timeout=90.0,
        )
    except httpx.TimeoutException:
        logger.warning(f"[卡拉彼丘·对局分析] 获取对局 {room_id} 统计超时")
        raise DakanuError("对局回放解析超时，请稍后再试。") from None
    except httpx.HTTPError as exc:
        logger.warning(f"[卡拉彼丘·对局分析] 请求对局 {room_id} 统计失败：{exc}")
        raise DakanuError("获取对局分析数据失败，请稍后再试。") from None

    if response.status_code == 404:
        raise DakanuError(f"没有找到对局 {room_id} 的回放统计数据。")
    if response.status_code == 429:
        raise DakanuError(format_rate_limit_message(response, prefix="对局分析请求过于频繁"))
    if response.status_code in {502, 503, 504}:
        raise DakanuError("战绩站暂时无法解析该对局，请稍后再试。")
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·对局分析] 对局 {room_id} 统计返回 HTTP {response.status_code}")
        raise DakanuError(safe_error_text(response) or "获取对局分析数据失败，请稍后再试。")

    raw_text = response.text
    try:
        payload: Any = json.loads(raw_text)
    except ValueError:
        logger.warning(f"[卡拉彼丘·对局分析] 对局 {room_id} 统计返回非 JSON 响应")
        raise DakanuError("对局分析数据格式异常，请稍后再试。") from None
    if isinstance(payload, dict) and payload.get("ok") is not True:
        err = payload.get("error")
        if isinstance(err, str) and err.strip() and "<" not in err:
            raise DakanuError(err.strip())
        raise DakanuError("战绩站暂未提供该对局的分析数据。")

    parsed = parse_match_statistics(payload)
    if parsed is None:
        logger.warning(f"[卡拉彼丘·对局分析] 对局 {room_id} 统计响应结构异常")
        raise DakanuError("对局分析数据格式异常，请稍后再试。")
    return DakanuMatchStatisticsPayload(stats=parsed, raw_json=raw_text)


async def fetch_match_statistics(room_id: str, *, region: str = "cn") -> DakanuMatchStatistics:
    """获取单场对局的回放解析全局统计数据。"""
    result = await fetch_match_statistics_payload(room_id, region=region)
    return result.stats
