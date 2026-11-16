"""Dakanu 公开读取接口。"""

import time
import asyncio
from typing import TypedDict, NotRequired

import httpx

from gsuid_core.pool import to_thread
from gsuid_core.logger import logger

BASE_URL = "https://www.dakanu.com"
_REFRESH_POLL_INTERVAL = 2.0
_REFRESH_TIMEOUT = 300.0


class DakanuMedal(TypedDict, total=False):
    id: int
    axis: list[int] | None
    zoomScale: float | None
    rotateScale: float | None
    levelFlip: bool
    level: int | None


class DakanuPlayerTag(TypedDict, total=False):
    id: str
    label: str
    tone: str
    description: str


class DakanuPlayer(TypedDict):
    id: str
    nickname: str
    clanId: str
    previousNames: list[str]
    level: int
    exp: int
    laud: int
    avatarId: int
    borderId: int
    privacyStatus: str
    accountVerified: bool
    medals: NotRequired[list[DakanuMedal | int]]
    tags: NotRequired[list[DakanuPlayerTag]]


class DakanuPlayerSuggestion(TypedDict):
    playerId: str
    nickname: str
    matchedName: str
    matchedBy: str
    level: int | None
    icon: int | None
    exact: bool
    indexed: bool


class DakanuPresence(TypedDict):
    state: str
    onlineStatus: int | str | None
    lastOnlineAt: int | None
    lastActiveAt: int | None
    statusText: NotRequired[str | None]
    regionLabel: NotRequired[str | None]
    leisureScore: NotRequired[int | None]
    leisureSegment: NotRequired[int | None]
    stars: NotRequired[int | None]
    winGames: NotRequired[int | None]
    mvpCount: NotRequired[int | None]
    totalGames: NotRequired[int | None]


class DakanuRank(TypedDict):
    segment: int
    topSegment: int
    historicalSegment: int
    historicalSegmentSeason: int
    historicalSegmentPos: int | None
    divisionScore: int
    topDivisionScore: int
    gradeScore: int
    topGradeScore: int
    rankPos: int | None
    topRankPos: int | None
    likeCount: int


class DakanuSummary(TypedDict):
    rounds: int
    wins: int
    losses: int
    winRate: float
    kills: int
    assists: int
    deaths: int
    kd: float
    kda: float
    damage: int
    avgDamage: float
    roundAveDamage: float
    avgKill: float
    avgAssist: float
    avgDeath: float
    mvpCount: int
    mvpRate: float
    headshotRate: float


class DakanuMode(TypedDict):
    mode: str
    label: str
    rounds: int
    wins: int
    winRate: float
    kd: float
    kills: NotRequired[int | None]
    assists: NotRequired[int | None]
    deaths: NotRequired[int | None]
    damage: NotRequired[int | None]
    kda: NotRequired[float | None]
    avgDamage: float
    roundAveDamage: float
    avgKill: float
    avgAssist: float | None
    avgDeath: NotRequired[float]
    headshotRate: float
    mvpCount: int | None
    mvpRate: float


class DakanuRole(TypedDict):
    roleId: int
    name: str
    count: int
    wins: int
    winRate: float
    kills: int
    deaths: int
    kd: float
    damage: int
    avgDamage: float
    maxKill: int
    maxDamage: int


class DakanuMatch(TypedDict):
    roomId: str
    mode: str
    modeLabel: str
    playMode: str
    mapId: int
    roleId: int
    result: str
    myScore: int | None
    opponentScore: int | None
    durationSeconds: int
    playedAt: int
    myRanking: int | None
    mvp: bool
    svp: bool
    divisionScore: int | None
    divisionScoreDelta: int | None
    kills: int
    deaths: int
    assists: int
    teamKills: int | None


class DakanuMatchPlayer(TypedDict):
    playerId: str
    nickname: str
    avatarId: int
    teamId: str
    teamLabel: str
    roleId: int
    roleName: str
    kills: int
    knockdowns: int | None
    assists: int
    deaths: int
    damage: int
    score: int
    personalScore: int | None
    strategyScore: int | None
    teamworkScore: int | None
    result: str
    mvp: bool
    svp: bool
    isTarget: bool


class DakanuMatchTeam(TypedDict):
    id: str
    label: str
    players: list[DakanuMatchPlayer]


class DakanuMatchDetail(TypedDict, total=False):
    ok: bool
    roomId: str
    summary: object | None
    teams: list[DakanuMatchTeam]
    rounds: list[object]
    hasDetail: bool
    viewerPlayerId: str | None
    scoreboardViewerPlayerId: str | None
    upstreamCode: int
    viewerFallback: object | None
    cached: bool


class DakanuRefreshError(TypedDict):
    message: str
    code: str
    status: int


class DakanuRefreshJob(TypedDict, total=False):
    state: str
    startedAt: int
    finishedAt: int
    error: DakanuRefreshError
    warning: dict[str, str]


class DakanuRefreshResponse(TypedDict):
    ok: bool
    job: DakanuRefreshJob


class DakanuMeta(TypedDict):
    cached: bool
    source: str
    currentSeason: str
    matchesTotal: int
    detailsAvailable: int
    warnings: list[str]
    fetchedAt: int
    stale: str | None
    observedMatches: int
    lastCheckedAt: int


class DakanuTeamUp(TypedDict):
    playerId: str
    nickname: str
    avatarId: int
    teamedGames: int
    teamedWins: int
    teamedLosses: int
    teamedDraws: int
    teamedWinRate: float
    lastWinAt: int | None
    latestRoomId: str | None


class DakanuRival(TypedDict):
    playerId: str
    nickname: str
    avatarId: int
    games: int
    wins: int
    losses: int
    draws: int
    winRate: float
    lastPlayedAt: int | None
    latestRoomId: str | None


class DakanuProfile(TypedDict):
    player: DakanuPlayer
    presence: DakanuPresence
    rank: DakanuRank
    summary: DakanuSummary
    modes: list[DakanuMode]
    roles: list[DakanuRole]
    matches: list[DakanuMatch]
    historyMatches: list[DakanuMatch]
    teamUps: list[DakanuTeamUp]
    rivals: list[DakanuRival]
    meta: DakanuMeta


class DakanuProfileResponse(TypedDict):
    ok: bool
    profile: DakanuProfile


class DakanuClanIcon(TypedDict):
    bgId: int
    bgColor: int
    imageId: int
    imageColor: int


class DakanuClan(TypedDict):
    clanId: str
    name: str
    level: int
    memberCount: int
    icon: DakanuClanIcon
    intro: str


class DakanuClanSearch(TypedDict):
    ok: bool
    count: int
    clans: list[DakanuClan]


class DakanuFavoriteMode(TypedDict):
    mode: str
    label: str


class DakanuActivityPoint(TypedDict):
    at: int
    index: float


class DakanuActivityEstimatePoint(TypedDict):
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


class DakanuActivityEstimate(TypedDict):
    updatedAt: int
    points: list[DakanuActivityEstimatePoint]


class DakanuGameActivity(TypedDict):
    ok: bool
    range: str
    intervalSeconds: int
    updatedAt: int
    sparse: bool
    region: str
    estimate: DakanuActivityEstimate
    points: list[DakanuActivityPoint]


class DakanuChatSelection(TypedDict):
    channel: int | None
    population: int | None
    reason: str | None


class DakanuChatScope(TypedDict):
    include_empty: bool
    channel_count: int
    active_channels: int
    requested_channels: int
    selected_channels: int


class DakanuChatMessage(TypedDict):
    channel: int
    player_id: str
    nick: str
    message: str
    sent_at: int
    icon: int | None
    icon_frame: int | None
    vc_border_id: int | None
    bubble_id: int | None
    level: int | None
    target_id: str | None


class DakanuChatAggregate(TypedDict):
    ok: bool
    generated_at: int
    scope: DakanuChatScope
    strategy: str
    selection: DakanuChatSelection
    messages: list[DakanuChatMessage]
    count: int
    elapsed_seconds: float


class DakanuLeisure(TypedDict, total=False):
    score: int
    segment: int
    star: int
    starScore: int
    battles: int
    wins: int
    winRate: float
    mvpCount: int
    favoriteModes: list[DakanuFavoriteMode]
    favoriteRoles: list[int]


_ROLE_SLUGS: dict[int, str] = {
    101: "michele",
    105: "audrey",
    107: "maddelena",
    108: "nobunaga",
    109: "reiichi",
    110: "bai_mo",
    112: "fuchsia",
    115: "flavia",
    119: "eika",
    120: "fragrans",
    121: "yugiri",
    122: "mara",
    123: "leona",
    124: "kokona",
    125: "qian_dai",
    126: "nono",
    128: "lawine",
    130: "xi",
    131: "yvette",
    132: "ming",
    133: "meredith",
    137: "kanami",
    146: "celestia",
    205: "galatea",
}


def role_image_url(role_id: int) -> str:
    """按角色 ID 返回站点角色立绘地址；未知角色返回空串。"""
    slug = _ROLE_SLUGS.get(role_id)
    return f"{BASE_URL}/roles/{slug}.webp" if slug else ""


def avatar_image_url(avatar_id: int) -> str:
    """按头像 ID 返回站点头像地址。"""
    return f"{BASE_URL}/avatars/{avatar_id}.webp"


def tier_image_url(tier_index: int) -> str:
    """按段位图标编号返回站点段位图标地址。"""
    return f"{BASE_URL}/tiers/tier-{tier_index}.png" if tier_index > 0 else ""


def challenge_tier_image_url(tier_index: int) -> str:
    """按挑战赛段位编号返回站点图标地址。"""
    return f"{BASE_URL}/challenge-rank/tier-{tier_index}.png" if 1 <= tier_index <= 9 else ""


def chat_emote_image_url(emote_id: str) -> str:
    """按聊天表情 ID 返回站点表情地址。"""
    cleaned = emote_id.strip().lstrip("#")
    return f"{BASE_URL}/chat-emotes/{cleaned}.webp" if cleaned.isascii() and cleaned.isdigit() else ""


def medal_image_url(medal_id: int) -> str:
    """按勋章 ID 返回站点勋章地址；非法 ID 返回空串。"""
    return f"{BASE_URL}/medals/{medal_id}.webp" if medal_id > 0 else ""


class DakanuError(Exception):
    """Dakanu 请求失败，message 可直接向用户说明原因。"""


def _is_profile_response(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if "ok" not in value or value["ok"] is not True:
        return False
    return "profile" in value and isinstance(value["profile"], dict)


@to_thread
def _fetch_profile_sync(player_id: str) -> DakanuProfile:
    """读取玩家缓存档案；不在查询链路里触发上游刷新。"""
    url = f"{BASE_URL}/api/summoner/{player_id}/cache"
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(url)
    if response.status_code == 204:
        raise DakanuError("没有找到这个玩家的战绩缓存。")
    if response.status_code == 404:
        raise DakanuError("没有找到这个玩家的战绩缓存。")
    if response.status_code == 429:
        raise DakanuError("查询过于频繁，请稍后再试。")
    if response.status_code in {502, 503, 504}:
        raise DakanuError("战绩站暂时无法读取数据，请稍后再试。")
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·战绩总览] 读取玩家 {player_id} 返回 HTTP {response.status_code}")
        raise DakanuError("读取战绩失败，请稍后再试。")
    try:
        payload: object = response.json()
    except ValueError:
        logger.warning(f"[卡拉彼丘·战绩总览] 玩家 {player_id} 返回非 JSON 响应")
        raise DakanuError("战绩数据格式异常，请稍后再试。") from None
    if not _is_profile_response(payload):
        logger.warning(f"[卡拉彼丘·战绩总览] 玩家 {player_id} 响应结构异常")
        raise DakanuError("战绩数据格式异常，请稍后再试。")
    return payload["profile"]


async def fetch_profile(player_id: str) -> DakanuProfile:
    """在线程池读取玩家缓存档案，避免阻塞事件循环。"""
    return await _fetch_profile_sync(player_id)


def _is_match_detail_response(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if "ok" not in value or value["ok"] is not True:
        return False
    if "roomId" not in value or not isinstance(value["roomId"], str):
        return False
    if "teams" not in value or not isinstance(value["teams"], list):
        return False
    return "rounds" in value and isinstance(value["rounds"], list)


@to_thread
def _fetch_match_detail_sync(player_id: str, room_id: str) -> DakanuMatchDetail | None:
    url = f"{BASE_URL}/api/match/{room_id}"
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(url, params={"player": player_id})
    if response.status_code == 404:
        return None
    if response.status_code == 429:
        raise DakanuError("对局详情查询过于频繁，请稍后再试。")
    if response.status_code in {502, 503, 504}:
        raise DakanuError("战绩站暂时无法读取对局详情，请稍后再试。")
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·最近对局] 读取对局 {room_id} 返回 HTTP {response.status_code}")
        return None
    try:
        payload: object = response.json()
    except ValueError:
        logger.warning(f"[卡拉彼丘·最近对局] 对局 {room_id} 返回非 JSON 响应")
        return None
    if not _is_match_detail_response(payload):
        logger.warning(f"[卡拉彼丘·最近对局] 对局 {room_id} 响应结构异常")
        return None
    details: DakanuMatchDetail = payload
    return details


async def fetch_match_detail(player_id: str, room_id: str) -> DakanuMatchDetail | None:
    """读取单场对局详情；无详情时返回 None。"""
    return await _fetch_match_detail_sync(player_id, room_id)


def _is_refresh_response(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if "ok" not in value or value["ok"] is not True:
        return False
    return "job" in value and isinstance(value["job"], dict)


@to_thread
def _start_refresh_sync(player_id: str) -> DakanuRefreshJob:
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.post(f"{BASE_URL}/api/summoner/{player_id}/refresh")
    if response.status_code == 404:
        raise DakanuError("没有找到该玩家的战绩数据。")
    if response.status_code == 429:
        raise DakanuError("查询过于频繁，请稍后再试。")
    if response.status_code in {502, 503, 504}:
        raise DakanuError("战绩站暂时无法查询，请稍后再试。")
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·刷新数据] 启动玩家 {player_id} 刷新返回 HTTP {response.status_code}")
        raise DakanuError("启动数据刷新失败，请稍后再试。")
    try:
        payload: object = response.json()
    except ValueError:
        logger.warning(f"[卡拉彼丘·刷新数据] 玩家 {player_id} 刷新响应不是 JSON")
        raise DakanuError("战绩数据格式异常，请稍后再试。") from None
    if not _is_refresh_response(payload):
        logger.warning(f"[卡拉彼丘·刷新数据] 玩家 {player_id} 刷新响应结构异常")
        raise DakanuError("战绩数据格式异常，请稍后再试。")
    return payload["job"]


async def start_profile_refresh(player_id: str) -> DakanuRefreshJob:
    return await _start_refresh_sync(player_id)


@to_thread
def _fetch_refresh_status_sync(player_id: str) -> DakanuRefreshJob:
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(f"{BASE_URL}/api/summoner/{player_id}/refresh")
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·刷新数据] 读取玩家 {player_id} 刷新状态返回 HTTP {response.status_code}")
        raise DakanuError("读取刷新状态失败，请稍后再试。")
    try:
        payload: object = response.json()
    except ValueError:
        logger.warning(f"[卡拉彼丘·刷新数据] 玩家 {player_id} 刷新状态不是 JSON")
        raise DakanuError("战绩数据格式异常，请稍后再试。") from None
    if not _is_refresh_response(payload):
        logger.warning(f"[卡拉彼丘·刷新数据] 玩家 {player_id} 刷新状态结构异常")
        raise DakanuError("战绩数据格式异常，请稍后再试。")
    return payload["job"]


async def fetch_refresh_status(player_id: str) -> DakanuRefreshJob:
    return await _fetch_refresh_status_sync(player_id)


async def refresh_profile(player_id: str) -> DakanuProfile:
    """启动刷新并等待缓存可读；缓存仍未生成时抛出 DakanuError。"""
    job = await start_profile_refresh(player_id)
    deadline = asyncio.get_running_loop().time() + _REFRESH_TIMEOUT
    while job["state"] == "running":
        if asyncio.get_running_loop().time() >= deadline:
            raise DakanuError("刷新仍在进行，请稍后用 kq战绩总览 查看。")
        await asyncio.sleep(_REFRESH_POLL_INTERVAL)
        job = await fetch_refresh_status(player_id)
    if job["state"] == "failed":
        error = job["error"]
        message = error["message"].strip()
        raise DakanuError(message or "战绩刷新失败，请稍后再试。")

    for _ in range(5):
        try:
            return await fetch_profile(player_id)
        except DakanuError as exc:
            if str(exc) != "没有找到这个玩家的战绩缓存。":
                raise
        await asyncio.sleep(_REFRESH_POLL_INTERVAL)
    raise DakanuError("刷新已完成，但暂时没有读到玩家缓存。")


def _is_clan_search(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if "ok" not in value or value["ok"] is not True:
        return False
    return "clans" in value and isinstance(value["clans"], list)


@to_thread
def _fetch_clan_sync(clan_id: str) -> DakanuClan | None:
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        response = client.get(f"{BASE_URL}/api/clans/search", params={"clan_id": clan_id, "limit": 1})
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·战绩总览] 读取战队 {clan_id} 返回 HTTP {response.status_code}")
        return None
    try:
        payload: object = response.json()
    except ValueError:
        logger.warning(f"[卡拉彼丘·战绩总览] 战队 {clan_id} 返回非 JSON 响应")
        return None
    if not _is_clan_search(payload):
        return None
    for clan in payload["clans"]:
        if not isinstance(clan, dict):
            continue
        if clan.get("clanId") != clan_id:
            continue
        return clan
    return None


async def fetch_clan(clan_id: str) -> DakanuClan | None:
    """按 clanId 读取战队信息；读取失败时不打断总览。"""
    if not clan_id:
        return None
    return await _fetch_clan_sync(clan_id)


def _is_leisure_response(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if "ok" not in value or value["ok"] is not True:
        return False
    return "leisure" in value and isinstance(value["leisure"], dict)


@to_thread
def _fetch_leisure_sync(player_id: str) -> DakanuLeisure | None:
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        response = client.get(f"{BASE_URL}/api/summoner/{player_id}/leisure", params={"season_id": 0})
    if response.status_code == 204:
        return None
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·战绩总览] 读取玩家 {player_id} 挑战赛数据返回 HTTP {response.status_code}")
        return None
    try:
        payload: object = response.json()
    except ValueError:
        logger.warning(f"[卡拉彼丘·战绩总览] 玩家 {player_id} 挑战赛数据不是 JSON")
        return None
    if not _is_leisure_response(payload):
        return None
    return payload["leisure"]


async def fetch_leisure(player_id: str) -> DakanuLeisure | None:
    """读取挑战赛数据；接口无数据时返回 None。"""
    return await _fetch_leisure_sync(player_id)


class DakanuRankType(TypedDict):
    code: int
    key: str
    label: str


class DakanuRankingEntry(TypedDict):
    position: int
    playerId: str
    nickname: str
    avatarId: int
    level: int
    borderId: int
    segment: int | None
    wins: int | None
    totalGames: int | None
    roles: list[int]
    score: int
    previousScore: int | None
    scoreDelta: int | None
    region: str | None
    province: str | None
    city: str | None
    cityCode: int | None


class DakanuRankingsBoard(TypedDict):
    ok: bool
    scope: str
    rankType: DakanuRankType
    metricLabel: str
    start: int
    end: int
    total: int
    day: str
    compareDay: str | None
    updatedAt: int
    cachedAt: int | None
    entries: list[DakanuRankingEntry]


class DakanuRankingFloorCurrent(TypedDict):
    day: str
    score: int
    position: int
    observedAt: int
    source: str


class DakanuRankingFloor(TypedDict):
    ok: bool
    region: str
    seasonId: int
    current: DakanuRankingFloorCurrent
    yesterdayDelta: int | None


class DakanuRankedSeason(TypedDict):
    season_id: int
    label: str
    current: bool


class DakanuCurrentSeason(TypedDict):
    ok: bool
    ranked_season: DakanuRankedSeason


class DakanuRolesRankingEntry(TypedDict):
    roleId: int
    games: int
    wins: int
    winRate: float
    appearanceRate: float
    players: int
    pickRate: float
    previousWinRate: float | None
    winRateDelta: float | None
    previousAppearanceRate: float | None
    appearanceRateDelta: float | None


class DakanuRolesRankingBoard(TypedDict):
    ok: bool
    scope: str
    rankedOnly: bool
    minGames: int
    day: str
    compareDay: str | None
    updatedAt: int
    coveredMatches: int
    entries: list[DakanuRolesRankingEntry]


_META_CACHE_TTL_SECONDS = 300.0
_meta_roles_cache: tuple[float, dict[int, str]] | None = None


def _as_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _as_str(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _opt_int(mapping: dict[object, object], key: str) -> int | None:
    if key not in mapping:
        return None
    return _as_int(mapping[key])


def _opt_str(mapping: dict[object, object], key: str) -> str | None:
    if key not in mapping:
        return None
    return _as_str(mapping[key])


def _opt_float(mapping: dict[object, object], key: str) -> float | None:
    if key not in mapping:
        return None
    return _as_float(mapping[key])


def _parse_ranking_entry(raw: object) -> DakanuRankingEntry | None:
    if not isinstance(raw, dict):
        return None
    position = _opt_int(raw, "position")
    player_id = _opt_str(raw, "playerId")
    nickname = _opt_str(raw, "nickname")
    avatar_id = _opt_int(raw, "avatarId")
    level = _opt_int(raw, "level")
    border_id = _opt_int(raw, "borderId")
    segment = _opt_int(raw, "segment")
    wins = _opt_int(raw, "wins")
    total_games = _opt_int(raw, "totalGames")
    score = _opt_int(raw, "score")
    raw_roles = raw["roles"] if "roles" in raw else None
    if (
        position is None
        or player_id is None
        or nickname is None
        or avatar_id is None
        or level is None
        or border_id is None
        or score is None
        or not isinstance(raw_roles, list)
    ):
        return None
    roles: list[int] = []
    for role_item in raw_roles:
        role_id = _as_int(role_item)
        if role_id is not None:
            roles.append(role_id)
    return {
        "position": position,
        "playerId": player_id,
        "nickname": nickname,
        "avatarId": avatar_id,
        "level": level,
        "borderId": border_id,
        "segment": segment,
        "wins": wins,
        "totalGames": total_games,
        "roles": roles,
        "score": score,
        "previousScore": _opt_int(raw, "previousScore"),
        "scoreDelta": _opt_int(raw, "scoreDelta"),
        "region": _opt_str(raw, "region"),
        "province": _opt_str(raw, "province"),
        "city": _opt_str(raw, "city"),
        "cityCode": _opt_int(raw, "cityCode"),
    }


def _parse_rankings_board(payload: object) -> DakanuRankingsBoard | None:
    if not isinstance(payload, dict) or "ok" not in payload or payload["ok"] is not True:
        return None
    raw_rank_type = payload["rankType"] if "rankType" in payload else None
    raw_entries = payload["entries"] if "entries" in payload else None
    if not isinstance(raw_rank_type, dict) or not isinstance(raw_entries, list):
        return None
    type_code = _opt_int(raw_rank_type, "code")
    type_key = _opt_str(raw_rank_type, "key")
    type_label = _opt_str(raw_rank_type, "label")
    scope = _opt_str(payload, "scope")
    metric_label = _opt_str(payload, "metricLabel")
    start = _opt_int(payload, "start")
    end = _opt_int(payload, "end")
    total = _opt_int(payload, "total")
    day = _opt_str(payload, "day")
    compare_day = _opt_str(payload, "compareDay")
    updated_at = _opt_int(payload, "updatedAt")
    cached_at = _opt_int(payload, "cachedAt")
    if (
        type_code is None
        or type_key is None
        or type_label is None
        or scope is None
        or metric_label is None
        or start is None
        or end is None
        or total is None
        or day is None
        or updated_at is None
    ):
        return None
    entries: list[DakanuRankingEntry] = []
    for item in raw_entries:
        entry = _parse_ranking_entry(item)
        if entry is not None:
            entries.append(entry)
    return {
        "ok": True,
        "scope": scope,
        "rankType": {"code": type_code, "key": type_key, "label": type_label},
        "metricLabel": metric_label,
        "start": start,
        "end": end,
        "total": total,
        "day": day,
        "compareDay": compare_day,
        "updatedAt": updated_at,
        "cachedAt": cached_at,
        "entries": entries,
    }


@to_thread
def _fetch_rankings_sync(
    rank_type: int,
    page: int,
    page_size: int,
    sub_type: int | None,
) -> DakanuRankingsBoard:
    params: dict[str, int] = {"type": rank_type, "page": page, "page_size": page_size}
    if sub_type is not None:
        params["sub_type"] = sub_type
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(
                f"{BASE_URL}/api/rankings",
                params=params,
            )
    except httpx.HTTPError as exc:
        logger.warning(f"[卡拉彼丘·排位排行] 请求榜单接口失败：{exc}")
        raise DakanuError("请求榜单失败，请稍后再试。") from None
    if response.status_code in {204, 404}:
        raise DakanuError("暂无榜单数据，请稍后再试。")
    if response.status_code == 429:
        raise DakanuError("查询过于频繁，请稍后再试。")
    if response.status_code in {502, 503, 504}:
        raise DakanuError("战绩站暂时无法读取榜单数据，请稍后再试。")
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·排位排行] 读取榜单返回 HTTP {response.status_code}")
        raise DakanuError("读取榜单失败，请稍后再试。")
    try:
        payload: object = response.json()
    except ValueError:
        logger.warning("[卡拉彼丘·排位排行] 榜单接口返回非 JSON 响应")
        raise DakanuError("榜单数据格式异常，请稍后再试。") from None
    board = _parse_rankings_board(payload)
    if board is None:
        logger.warning("[卡拉彼丘·排位排行] 榜单接口响应结构异常")
        raise DakanuError("榜单数据格式异常，请稍后再试。")
    return board


async def fetch_rankings(
    rank_type: int = 1,
    page: int = 1,
    page_size: int = 50,
    *,
    sub_type: int | None = None,
) -> DakanuRankingsBoard:
    """读取 Dakanu 在线排行榜数据。"""
    return await _fetch_rankings_sync(rank_type, page, page_size, sub_type)


def _parse_ranking_floor(payload: object) -> DakanuRankingFloor | None:
    if not isinstance(payload, dict) or "ok" not in payload or payload["ok"] is not True:
        return None
    region = _opt_str(payload, "region")
    season_id = _opt_int(payload, "seasonId")
    raw_current = payload["current"] if "current" in payload else None
    if region is None or season_id is None or not isinstance(raw_current, dict):
        return None
    day = _opt_str(raw_current, "day")
    score = _opt_int(raw_current, "score")
    position = _opt_int(raw_current, "position")
    observed_at = _opt_int(raw_current, "observedAt")
    source = _opt_str(raw_current, "source")
    if day is None or score is None or position is None or observed_at is None or source is None:
        return None
    return {
        "ok": True,
        "region": region,
        "seasonId": season_id,
        "current": {
            "day": day,
            "score": score,
            "position": position,
            "observedAt": observed_at,
            "source": source,
        },
        "yesterdayDelta": _opt_int(payload, "yesterdayDelta"),
    }


@to_thread
def _fetch_ranking_floor_sync(season_id: int) -> DakanuRankingFloor | None:
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(f"{BASE_URL}/api/rankings/floor", params={"season_id": season_id})
    except httpx.HTTPError as exc:
        logger.warning(f"[卡拉彼丘·排位排行] 请求奇点底分失败：{exc}")
        return None
    if response.status_code == 204:
        return None
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·排位排行] 读取奇点底分返回 HTTP {response.status_code}")
        return None
    try:
        payload: object = response.json()
    except ValueError:
        logger.warning("[卡拉彼丘·排位排行] 奇点底分返回非 JSON 响应")
        return None
    return _parse_ranking_floor(payload)


async def fetch_ranking_floor(season_id: int = 0) -> DakanuRankingFloor | None:
    """读取当前奇点底分；接口异常时返回 None，不阻断榜单渲染。"""
    return await _fetch_ranking_floor_sync(season_id)


def _parse_current_season(payload: object) -> DakanuCurrentSeason | None:
    if not isinstance(payload, dict) or "ok" not in payload or payload["ok"] is not True:
        return None
    raw_ranked = payload["ranked_season"] if "ranked_season" in payload else None
    if not isinstance(raw_ranked, dict):
        return None
    season_id = _opt_int(raw_ranked, "season_id")
    label = _opt_str(raw_ranked, "label")
    current = raw_ranked["current"] if "current" in raw_ranked else None
    if season_id is None or label is None or not isinstance(current, bool):
        return None
    return {
        "ok": True,
        "ranked_season": {
            "season_id": season_id,
            "label": label,
            "current": current,
        },
    }


@to_thread
def _fetch_current_season_sync() -> DakanuCurrentSeason | None:
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(f"{BASE_URL}/api/seasons/current")
    except httpx.HTTPError as exc:
        logger.warning(f"[卡拉彼丘·排位排行] 请求当前赛季失败：{exc}")
        return None
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·排位排行] 读取当前赛季返回 HTTP {response.status_code}")
        return None
    try:
        payload: object = response.json()
    except ValueError:
        logger.warning("[卡拉彼丘·排位排行] 当前赛季返回非 JSON 响应")
        return None
    return _parse_current_season(payload)


async def fetch_current_season() -> DakanuCurrentSeason | None:
    """读取当前排位赛季信息；接口异常时返回 None。"""
    return await _fetch_current_season_sync()


def _parse_roles_ranking_entry(raw: object) -> DakanuRolesRankingEntry | None:
    if not isinstance(raw, dict):
        return None
    role_id = _opt_int(raw, "roleId")
    games = _opt_int(raw, "games")
    wins = _opt_int(raw, "wins")
    win_rate = _opt_float(raw, "winRate")
    appearance_rate = _opt_float(raw, "appearanceRate")
    players = _opt_int(raw, "players")
    pick_rate = _opt_float(raw, "pickRate")
    if (
        role_id is None
        or games is None
        or wins is None
        or win_rate is None
        or appearance_rate is None
        or players is None
        or pick_rate is None
    ):
        return None
    return {
        "roleId": role_id,
        "games": games,
        "wins": wins,
        "winRate": win_rate,
        "appearanceRate": appearance_rate,
        "players": players,
        "pickRate": pick_rate,
        "previousWinRate": _opt_float(raw, "previousWinRate"),
        "winRateDelta": _opt_float(raw, "winRateDelta"),
        "previousAppearanceRate": _opt_float(raw, "previousAppearanceRate"),
        "appearanceRateDelta": _opt_float(raw, "appearanceRateDelta"),
    }


def _parse_roles_ranking_board(payload: object) -> DakanuRolesRankingBoard | None:
    if not isinstance(payload, dict) or "ok" not in payload or payload["ok"] is not True:
        return None
    raw_entries = payload["entries"] if "entries" in payload else None
    if not isinstance(raw_entries, list):
        return None
    scope = _opt_str(payload, "scope")
    ranked_only = payload["rankedOnly"] if "rankedOnly" in payload else None
    min_games = _opt_int(payload, "minGames")
    day = _opt_str(payload, "day")
    compare_day = _opt_str(payload, "compareDay")
    updated_at = _opt_int(payload, "updatedAt")
    covered_matches = _opt_int(payload, "coveredMatches")
    if (
        scope is None
        or not isinstance(ranked_only, bool)
        or min_games is None
        or day is None
        or updated_at is None
        or covered_matches is None
    ):
        return None
    entries: list[DakanuRolesRankingEntry] = []
    for item in raw_entries:
        entry = _parse_roles_ranking_entry(item)
        if entry is not None:
            entries.append(entry)
    return {
        "ok": True,
        "scope": scope,
        "rankedOnly": ranked_only,
        "minGames": min_games,
        "day": day,
        "compareDay": compare_day,
        "updatedAt": updated_at,
        "coveredMatches": covered_matches,
        "entries": entries,
    }


@to_thread
def _fetch_roles_ranking_sync(ranked_only: bool, min_games: int) -> DakanuRolesRankingBoard:
    params: dict[str, int] = {"min_games": min_games}
    if not ranked_only:
        params["all"] = 1
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(f"{BASE_URL}/api/roles/ranking", params=params)
    except httpx.HTTPError as exc:
        logger.warning(f"[卡拉彼丘·超弦体排行] 请求角色榜单失败：{exc}")
        raise DakanuError("请求超弦体排行失败，请稍后再试。") from None
    if response.status_code in {204, 404}:
        raise DakanuError("暂无超弦体排行数据，请稍后再试。")
    if response.status_code == 429:
        raise DakanuError("查询过于频繁，请稍后再试。")
    if response.status_code in {502, 503, 504}:
        raise DakanuError("战绩站暂时无法读取超弦体排行，请稍后再试。")
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·超弦体排行] 读取角色榜单返回 HTTP {response.status_code}")
        raise DakanuError("读取超弦体排行失败，请稍后再试。")
    try:
        payload: object = response.json()
    except ValueError:
        logger.warning("[卡拉彼丘·超弦体排行] 角色榜单返回非 JSON 响应")
        raise DakanuError("超弦体排行数据格式异常，请稍后再试。") from None
    board = _parse_roles_ranking_board(payload)
    if board is None:
        logger.warning("[卡拉彼丘·超弦体排行] 角色榜单响应结构异常")
        raise DakanuError("超弦体排行数据格式异常，请稍后再试。")
    return board


async def fetch_roles_ranking(*, ranked_only: bool = True, min_games: int = 3) -> DakanuRolesRankingBoard:
    """读取 Dakanu 超弦体胜率与登场率排行榜。"""
    return await _fetch_roles_ranking_sync(ranked_only, min_games)


@to_thread
def _fetch_meta_roles_sync() -> dict[int, str]:
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(f"{BASE_URL}/api/meta")
    except httpx.HTTPError as exc:
        logger.warning(f"[卡拉彼丘·角色字典] 请求 /api/meta 失败：{exc}")
        raise DakanuError("读取角色列表失败，请稍后再试。") from None
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·角色字典] 读取 /api/meta 返回 HTTP {response.status_code}")
        raise DakanuError("读取角色列表失败，请稍后再试。")
    try:
        payload: object = response.json()
    except ValueError:
        logger.warning("[卡拉彼丘·角色字典] /api/meta 返回非 JSON 响应")
        raise DakanuError("角色列表格式异常，请稍后再试。") from None
    if not isinstance(payload, dict) or "ok" not in payload or payload["ok"] is not True:
        raise DakanuError("角色列表格式异常，请稍后再试。")
    raw_roles = payload["roles"] if "roles" in payload else None
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
    global _meta_roles_cache
    now = time.monotonic()
    if _meta_roles_cache is not None and now < _meta_roles_cache[0]:
        return dict(_meta_roles_cache[1])
    roles = await _fetch_meta_roles_sync()
    _meta_roles_cache = (time.monotonic() + _META_CACHE_TTL_SECONDS, roles)
    return dict(roles)


def _opt_bool(mapping: dict[object, object], key: str) -> bool | None:
    if key not in mapping:
        return None
    value = mapping[key]
    return value if isinstance(value, bool) else None


def _parse_player_suggestion(raw: object) -> DakanuPlayerSuggestion | None:
    if not isinstance(raw, dict):
        return None
    player_id = _opt_str(raw, "playerId")
    nickname = _opt_str(raw, "nickname")
    matched_name = _opt_str(raw, "matchedName")
    matched_by = _opt_str(raw, "matchedBy")
    exact = _opt_bool(raw, "exact")
    indexed = _opt_bool(raw, "indexed")
    if (
        player_id is None
        or not player_id.isascii()
        or not player_id.isdigit()
        or nickname is None
        or matched_name is None
        or matched_by is None
        or exact is None
        or indexed is None
    ):
        return None
    return {
        "playerId": player_id,
        "nickname": nickname,
        "matchedName": matched_name,
        "matchedBy": matched_by,
        "level": _opt_int(raw, "level"),
        "icon": _opt_int(raw, "icon"),
        "exact": exact,
        "indexed": indexed,
    }


@to_thread
def _fetch_search_players_sync(query: str) -> list[DakanuPlayerSuggestion]:
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(f"{BASE_URL}/api/search/players", params={"q": query})
    except httpx.HTTPError as exc:
        logger.warning(f"[卡拉彼丘·玩家搜索] 搜索玩家 {query} 失败：{exc}")
        raise DakanuError("搜索玩家失败，请稍后再试。") from None
    if response.status_code == 429:
        raise DakanuError("查询过于频繁，请稍后再试。")
    if response.status_code in {502, 503, 504}:
        raise DakanuError("战绩站暂时无法搜索玩家，请稍后再试。")
    if response.status_code != 200:
        logger.warning(f"[卡拉彼丘·玩家搜索] 搜索玩家 {query} 返回 HTTP {response.status_code}")
        raise DakanuError("搜索玩家失败，请稍后再试。")
    try:
        payload: object = response.json()
    except ValueError:
        logger.warning(f"[卡拉彼丘·玩家搜索] 搜索玩家 {query} 返回非 JSON 响应")
        raise DakanuError("玩家搜索结果格式异常，请稍后再试。") from None
    if not isinstance(payload, dict) or "ok" not in payload or payload["ok"] is not True:
        raise DakanuError("玩家搜索结果格式异常，请稍后再试。")
    raw_suggestions = payload["suggestions"] if "suggestions" in payload else None
    if not isinstance(raw_suggestions, list):
        raise DakanuError("玩家搜索结果格式异常，请稍后再试。")
    suggestions: list[DakanuPlayerSuggestion] = []
    for item in raw_suggestions:
        parsed = _parse_player_suggestion(item)
        if parsed is not None:
            suggestions.append(parsed)
    return suggestions


async def search_players(query: str) -> list[DakanuPlayerSuggestion]:
    """按昵称或 UID 搜索 Dakanu 玩家候选。"""
    cleaned = query.strip()
    if not cleaned:
        return []
    return await _fetch_search_players_sync(cleaned)


_GAME_ACTIVITY_RANGES = frozenset({"6h", "24h", "7d", "30d"})


def _request_json_get(
    path: str,
    params: dict[str, str] | dict[str, int],
    *,
    log_tag: str,
    label: str,
) -> object:
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(f"{BASE_URL}{path}", params=params)
    except httpx.HTTPError as exc:
        logger.warning(f"{log_tag} 请求{label}失败：{exc}")
        raise DakanuError(f"请求{label}失败，请稍后再试。") from None
    if response.status_code in {204, 404}:
        raise DakanuError(f"暂无{label}数据，请稍后再试。")
    if response.status_code == 429:
        raise DakanuError("查询过于频繁，请稍后再试。")
    if response.status_code in {502, 503, 504}:
        raise DakanuError(f"战绩站暂时无法读取{label}，请稍后再试。")
    if response.status_code != 200:
        logger.warning(f"{log_tag} 读取{label}返回 HTTP {response.status_code}")
        raise DakanuError(f"读取{label}失败，请稍后再试。")
    try:
        return response.json()
    except ValueError:
        logger.warning(f"{log_tag} {label}返回非 JSON 响应")
        raise DakanuError(f"{label}数据格式异常，请稍后再试。") from None


def _parse_activity_point(raw: object) -> DakanuActivityPoint | None:
    if not isinstance(raw, dict):
        return None
    at = _opt_int(raw, "at")
    index_val = _opt_float(raw, "index")
    if at is None or index_val is None:
        return None
    return {"at": at, "index": index_val}


def _parse_activity_estimate_point(raw: object) -> DakanuActivityEstimatePoint | None:
    if not isinstance(raw, dict):
        return None
    at = _opt_int(raw, "at")
    floor_val = _opt_int(raw, "floor")
    gap = _opt_int(raw, "gap")
    channel = _opt_int(raw, "channel")
    daily = _opt_int(raw, "daily")
    complete_players = _opt_int(raw, "completePlayers")
    complete_seats = _opt_int(raw, "completeSeats")
    partial_rooms = _opt_int(raw, "partialRooms")
    coverage = _opt_float(raw, "coverage")
    active_30d = _opt_int(raw, "active30d")
    if (
        at is None
        or floor_val is None
        or gap is None
        or channel is None
        or daily is None
        or complete_players is None
        or complete_seats is None
        or partial_rooms is None
        or coverage is None
        or active_30d is None
    ):
        return None
    return {
        "at": at,
        "floor": floor_val,
        "gap": gap,
        "channel": channel,
        "daily": daily,
        "completePlayers": complete_players,
        "completeSeats": complete_seats,
        "partialRooms": partial_rooms,
        "coverage": coverage,
        "active30d": active_30d,
    }


def _parse_game_activity(payload: object) -> DakanuGameActivity | None:
    if not isinstance(payload, dict) or "ok" not in payload or payload["ok"] is not True:
        return None
    range_val = _opt_str(payload, "range")
    interval_seconds = _opt_int(payload, "intervalSeconds")
    updated_at = _opt_int(payload, "updatedAt")
    sparse = _opt_bool(payload, "sparse")
    region = _opt_str(payload, "region")
    raw_estimate = payload["estimate"] if "estimate" in payload else None
    raw_points = payload["points"] if "points" in payload else None
    if (
        range_val is None
        or interval_seconds is None
        or updated_at is None
        or sparse is None
        or region is None
        or not isinstance(raw_estimate, dict)
        or not isinstance(raw_points, list)
    ):
        return None
    est_updated_at = _opt_int(raw_estimate, "updatedAt")
    raw_est_points = raw_estimate["points"] if "points" in raw_estimate else None
    if est_updated_at is None or not isinstance(raw_est_points, list):
        return None
    est_points: list[DakanuActivityEstimatePoint] = []
    for item in raw_est_points:
        parsed_est = _parse_activity_estimate_point(item)
        if parsed_est is not None:
            est_points.append(parsed_est)
    points: list[DakanuActivityPoint] = []
    for item in raw_points:
        parsed_pt = _parse_activity_point(item)
        if parsed_pt is not None:
            points.append(parsed_pt)
    return {
        "ok": True,
        "range": range_val,
        "intervalSeconds": interval_seconds,
        "updatedAt": updated_at,
        "sparse": sparse,
        "region": region,
        "estimate": {"updatedAt": est_updated_at, "points": est_points},
        "points": points,
    }


@to_thread
def _fetch_game_activity_sync(range_key: str) -> DakanuGameActivity:
    payload = _request_json_get(
        "/api/activity/game",
        {"range": range_key},
        log_tag="[卡拉彼丘·活跃趋势]",
        label="玩家活跃趋势",
    )
    activity = _parse_game_activity(payload)
    if activity is None:
        logger.warning("[卡拉彼丘·活跃趋势] 接口响应结构异常")
        raise DakanuError("玩家活跃趋势数据格式异常，请稍后再试。")
    return activity


async def fetch_game_activity(range_key: str = "24h") -> DakanuGameActivity:
    """读取 Dakanu 玩家活跃趋势数据。"""
    if range_key not in _GAME_ACTIVITY_RANGES:
        raise ValueError(f"不支持的活跃范围：{range_key}")
    return await _fetch_game_activity_sync(range_key)


def _parse_chat_message(raw: object) -> DakanuChatMessage | None:
    if not isinstance(raw, dict):
        return None
    channel = _opt_int(raw, "channel")
    player_id = _opt_str(raw, "player_id")
    nick = _opt_str(raw, "nick")
    message = _opt_str(raw, "message")
    sent_at = _opt_int(raw, "sent_at")
    if (
        channel is None
        or player_id is None
        or nick is None
        or message is None
        or sent_at is None
    ):
        return None
    return {
        "channel": channel,
        "player_id": player_id,
        "nick": nick,
        "message": message,
        "sent_at": sent_at,
        "icon": _opt_int(raw, "icon"),
        "icon_frame": _opt_int(raw, "icon_frame"),
        "vc_border_id": _opt_int(raw, "vc_border_id"),
        "bubble_id": _opt_int(raw, "bubble_id"),
        "level": _opt_int(raw, "level"),
        "target_id": _opt_str(raw, "target_id"),
    }


def _parse_chat_scope(raw: object) -> DakanuChatScope | None:
    if not isinstance(raw, dict):
        return None
    include_empty = _opt_bool(raw, "include_empty")
    channel_count = _opt_int(raw, "channel_count")
    active_channels = _opt_int(raw, "active_channels")
    requested_channels = _opt_int(raw, "requested_channels")
    selected_channels = _opt_int(raw, "selected_channels")
    if (
        include_empty is None
        or channel_count is None
        or active_channels is None
        or requested_channels is None
        or selected_channels is None
    ):
        return None
    return {
        "include_empty": include_empty,
        "channel_count": channel_count,
        "active_channels": active_channels,
        "requested_channels": requested_channels,
        "selected_channels": selected_channels,
    }


def _parse_chat_aggregate(payload: object) -> DakanuChatAggregate | None:
    if not isinstance(payload, dict) or "ok" not in payload or payload["ok"] is not True:
        return None
    generated_at = _opt_int(payload, "generated_at")
    strategy = _opt_str(payload, "strategy")
    count = _opt_int(payload, "count")
    elapsed_seconds = _opt_float(payload, "elapsed_seconds")
    raw_scope = payload["scope"] if "scope" in payload else None
    raw_selection = payload["selection"] if "selection" in payload else None
    raw_messages = payload["messages"] if "messages" in payload else None
    scope = _parse_chat_scope(raw_scope)
    if (
        generated_at is None
        or scope is None
        or strategy is None
        or count is None
        or elapsed_seconds is None
        or not isinstance(raw_selection, dict)
        or not isinstance(raw_messages, list)
    ):
        return None
    sel_channel = _opt_int(raw_selection, "channel")
    sel_population = _opt_int(raw_selection, "population")
    sel_reason = _opt_str(raw_selection, "reason")
    messages: list[DakanuChatMessage] = []
    for item in raw_messages:
        parsed = _parse_chat_message(item)
        if parsed is not None:
            messages.append(parsed)
    return {
        "ok": True,
        "generated_at": generated_at,
        "scope": scope,
        "strategy": strategy,
        "selection": {
            "channel": sel_channel,
            "population": sel_population,
            "reason": sel_reason,
        },
        "messages": messages,
        "count": count,
        "elapsed_seconds": elapsed_seconds,
    }


@to_thread
def _fetch_chat_aggregate_sync(limit_per_channel: int) -> DakanuChatAggregate:
    payload = _request_json_get(
        "/api/chat/messages/aggregate",
        {"limit_per_channel": limit_per_channel},
        log_tag="[卡拉彼丘·世界聊天]",
        label="世界频道动态",
    )
    aggregate = _parse_chat_aggregate(payload)
    if aggregate is None:
        logger.warning("[卡拉彼丘·世界聊天] 接口响应结构异常")
        raise DakanuError("世界频道动态数据格式异常，请稍后再试。")
    return aggregate


async def fetch_chat_aggregate(limit_per_channel: int = 30) -> DakanuChatAggregate:
    """读取 Dakanu 世界频道聚合消息。"""
    return await _fetch_chat_aggregate_sync(limit_per_channel)
