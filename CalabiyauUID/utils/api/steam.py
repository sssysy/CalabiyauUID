"""SteamCMD 公开游戏资产查询接口。"""

import re
from dataclasses import dataclass

import httpx

from gsuid_core.logger import logger

STEAM_APP_ID = "1282270"
STEAMCMD_INFO_URL = f"https://api.steamcmd.net/v1/info/{STEAM_APP_ID}"
STEAM_CDN_PREFIX = f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{STEAM_APP_ID}/"
_SAFE_REL_PATH = re.compile(r"^(?P<asset_hash>[0-9a-fA-F]{16,64})/[A-Za-z0-9._-]+$")
_LOG_TAG = "[卡拉彼丘·帮助背景]"


@dataclass(frozen=True)
class SteamHelpAssets:
    """从 SteamCMD 解析出的帮助图背景资产信息。"""

    banner_hash: str
    banner_url: str
    bg_hash: str
    bg_url: str


def _read_dict(mapping: dict[object, object], key: str) -> dict[object, object] | None:
    if key not in mapping:
        return None
    value = mapping[key]
    if isinstance(value, dict):
        return value
    return None


def _extract_image2x_english(assets_full: dict[object, object], field: str) -> tuple[str, str] | None:
    section = _read_dict(assets_full, field)
    if section is None:
        return None
    image2x = _read_dict(section, "image2x")
    if image2x is None or "english" not in image2x:
        return None
    rel_path = image2x["english"]
    if not isinstance(rel_path, str):
        return None
    match = _SAFE_REL_PATH.fullmatch(rel_path.strip())
    if match is None:
        return None
    return match.group("asset_hash"), f"{STEAM_CDN_PREFIX}{rel_path.strip()}"


def parse_steam_help_assets(payload: object) -> SteamHelpAssets | None:
    """解析 SteamCMD 响应中的 library_hero 与 library_capsule 资源路径。"""
    if not isinstance(payload, dict):
        return None
    data = _read_dict(payload, "data")
    if data is None:
        return None
    app_info = _read_dict(data, STEAM_APP_ID)
    if app_info is None:
        return None
    common = _read_dict(app_info, "common")
    if common is None:
        return None
    assets_full = _read_dict(common, "library_assets_full")
    if assets_full is None:
        return None

    hero = _extract_image2x_english(assets_full, "library_hero")
    capsule = _extract_image2x_english(assets_full, "library_capsule")
    if hero is None or capsule is None:
        return None
    return SteamHelpAssets(
        banner_hash=hero[0],
        banner_url=hero[1],
        bg_hash=capsule[0],
        bg_url=capsule[1],
    )


async def fetch_steam_help_assets() -> SteamHelpAssets | None:
    """联网获取卡拉彼丘 SteamCMD 资产链接与版本 hash，失败返回 None。"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(STEAMCMD_INFO_URL)
            response.raise_for_status()
            payload: object = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(f"{_LOG_TAG} 请求 SteamCMD 失败：{exc}")
        return None

    assets = parse_steam_help_assets(payload)
    if assets is None:
        logger.warning(f"{_LOG_TAG} SteamCMD 返回缺少 library_hero/library_capsule 字段")
        return None
    return assets
