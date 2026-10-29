"""插件数据目录。"""

from pathlib import Path

from gsuid_core.data_store import get_res_path

DATA_DIR: Path = get_res_path("CalabiyauUID")
