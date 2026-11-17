from pathlib import Path

from gsuid_core.data_store import get_res_path

DATA_DIR: Path = get_res_path("CalabiyauUID")
CONFIG_PATH: Path = DATA_DIR / "config.json"
RESOURCE_DIR: Path = Path(__file__).resolve().parents[1] / "resources"
ASSET_DIR: Path = RESOURCE_DIR / "assets"
