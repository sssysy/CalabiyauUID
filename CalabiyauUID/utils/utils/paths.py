from pathlib import Path

from gsuid_core.data_store import get_res_path

DATA_DIR: Path = get_res_path("CalabiyauUID")
CONFIG_PATH: Path = DATA_DIR / "config.json"
CUSTOM_BG_PATH: Path = DATA_DIR / "bg.png"
PLAYER_DATA_DIR: Path = DATA_DIR / "player_data"
IMG_CACHE_DIR: Path = DATA_DIR / "img_cache"
CACHE_DIR: Path = DATA_DIR / "cache"
RESOURCE_DIR: Path = Path(__file__).resolve().parents[1] / "resources"
ASSET_DIR: Path = RESOURCE_DIR / "assets"
STICKER_DIR: Path = RESOURCE_DIR / "stickers"
