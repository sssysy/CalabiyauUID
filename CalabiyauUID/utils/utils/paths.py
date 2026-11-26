from pathlib import Path

from gsuid_core.data_store import get_res_path

DATA_DIR: Path = get_res_path("CalabiyauUID")
CONFIG_PATH: Path = DATA_DIR / "config.json"
CUSTOM_BG_PATH: Path = DATA_DIR / "bg.png"
PLAYER_DATA_DIR: Path = DATA_DIR / "player_data"
IMG_CACHE_DIR: Path = DATA_DIR / "img_cache"
CACHE_DIR: Path = DATA_DIR / "cache"
MATCH_DETAIL_CACHE_DIR: Path = CACHE_DIR / "match_detail" / "v1"
MATCH_STATS_CACHE_DIR: Path = CACHE_DIR / "match_stats" / "v1"
RESOURCE_DIR: Path = DATA_DIR / "resources"
ASSET_DIR: Path = RESOURCE_DIR / "assets"
STICKER_DIR: Path = RESOURCE_DIR / "stickers"
