"""CalabiyauUID 控制台配置定义与类型安全读取。"""

from gsuid_core.utils.plugins_config.models import GSC, GsBoolConfig
from gsuid_core.utils.plugins_config.gs_config import StringConfig

from ..utils.paths import DATA_DIR

CONFIG_PATH = DATA_DIR / "config.json"

CONFIG_DEFAULT: dict[str, GSC] = {
    "ReplayUseFileURI": GsBoolConfig(
        "使用 file:// 发送回放文件",
        "开启后可以解决大文件发送失败的问题，但是要求对应目录位置对协议端可达",
        False,
    ),
}

CalabiyauConfig = StringConfig("CalabiyauUID", CONFIG_PATH, CONFIG_DEFAULT)


def use_file_uri_for_replay() -> bool:
    """是否改用 file:// URI 发送本地回放文件。"""
    item = CalabiyauConfig.get_config("ReplayUseFileURI")
    if not isinstance(item, GsBoolConfig):
        raise TypeError("ReplayUseFileURI 配置类型异常")
    return bool(item.data)
