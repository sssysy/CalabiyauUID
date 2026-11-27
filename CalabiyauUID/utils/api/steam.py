import re
from typing import Any
from dataclasses import dataclass

import httpx
from pydantic import Field, AliasPath, BaseModel, ConfigDict, ValidationError

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


class _SteamHelpPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    hero_path: str = Field(
        validation_alias=AliasPath(
            "data", STEAM_APP_ID, "common", "library_assets_full", "library_hero", "image2x", "english"
        )
    )
    capsule_path: str = Field(
        validation_alias=AliasPath(
            "data", STEAM_APP_ID, "common", "library_assets_full", "library_capsule", "image2x", "english"
        )
    )


def _parse_asset_path(rel_path: str) -> tuple[str, str] | None:
    cleaned = rel_path.strip()
    match = _SAFE_REL_PATH.fullmatch(cleaned)
    if match is None:
        return None
    return match.group("asset_hash"), f"{STEAM_CDN_PREFIX}{cleaned}"


def parse_steam_help_assets(payload: Any) -> SteamHelpAssets | None:
    """解析 SteamCMD 响应中的 library_hero 与 library_capsule 资源路径。"""
    try:
        parsed = _SteamHelpPayload.model_validate(payload)
    except ValidationError:
        return None

    hero = _parse_asset_path(parsed.hero_path)
    capsule = _parse_asset_path(parsed.capsule_path)
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
            payload: Any = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(f"{_LOG_TAG} 请求 SteamCMD 失败：{exc}")
        return None

    assets = parse_steam_help_assets(payload)
    if assets is None:
        logger.warning(f"{_LOG_TAG} SteamCMD 返回缺少 library_hero/library_capsule 字段")
        return None
    return assets
