from gsuid_core.utils.plugins_config.models import GSC, GsBoolConfig

CONFIG_DEFAULT: dict[str, GSC] = {
    "ReplayUseFileURI": GsBoolConfig(
        "使用 file:// 发送回放文件",
        "开启后可以解决大文件发送失败的问题，但是要求对应目录位置对协议端可达",
        False,
    ),
}
