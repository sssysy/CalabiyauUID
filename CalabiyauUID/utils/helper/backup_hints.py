"""注册 CalabiyauUID 的备份建议路径。"""

from gsuid_core.logger import logger

from ..utils.paths import CACHE_DIR, CONFIG_PATH, IMG_CACHE_DIR, PLAYER_DATA_DIR

_PLUGIN_NAME = "CalabiyauUID"


def register_calabiyau_backup_hints() -> None:
    """向 GsCore 备份系统登记用户数据、配置与可重新下载的缓存目录。"""
    try:
        from gsuid_core.utils.backup.hints import register_backup_path
    except ImportError:
        logger.debug("[卡拉彼丘·备份注册] 当前 GsCore 版本不支持备份建议注册，已跳过")
        return

    register_backup_path(
        _PLUGIN_NAME,
        PLAYER_DATA_DIR,
        "user_data",
        "玩家战绩快照",
    )
    register_backup_path(
        _PLUGIN_NAME,
        CONFIG_PATH,
        "config",
        "插件配置",
        default_selected=True,
    )
    register_backup_path(
        _PLUGIN_NAME,
        IMG_CACHE_DIR,
        "regenerable",
        "图片缓存",
    )
    register_backup_path(
        _PLUGIN_NAME,
        CACHE_DIR,
        "regenerable",
        "对局回放等临时缓存文件",
    )
