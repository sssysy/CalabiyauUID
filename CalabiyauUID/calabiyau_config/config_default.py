from gsuid_core.utils.plugins_config.models import GSC, GsBoolConfig, GsImageConfig

from ..utils.utils.paths import DATA_DIR, CUSTOM_BG_PATH

CONFIG_DEFAULT: dict[str, GSC] = {
    "ReplayUseFileURI": GsBoolConfig(
        "使用 file:// 发送回放文件",
        "开启后可以解决大文件发送失败的问题，但是要求对应目录位置对协议端可达",
        False,
    ),
    "CustomBgPath": GsImageConfig(
        "自定义背景图片",
        "卡片渲染的自定义背景图片，未设置时默认使用赛季高斯模糊背景",
        str(CUSTOM_BG_PATH),
        str(DATA_DIR),
        "bg",
        "png",
    ),
}
