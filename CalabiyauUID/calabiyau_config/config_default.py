from gsuid_core.utils.plugins_config.models import GSC, GsIntConfig, GsStrConfig, GsBoolConfig, GsImageConfig

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
    "FanbookLoginUrl": GsStrConfig(
        "Fanbook登录页面URL",
        "登录页对外访问地址（可含协议与端口），留空则使用 Core 的 HOST/PORT 并自动探测公网 IP",
        "",
    ),
    "FanbookLoginTTL": GsIntConfig(
        "Fanbook登录会话存活秒数",
        "发送登录链接后多久内需完成登录（秒），超时后清理会话，最大 3600",
        600,
        max_value=3600,
    ),
    "FanbookQRLogin": GsBoolConfig(
        "Fanbook登录链接转二维码",
        "开启后把 Fanbook 登录页面链接生成二维码图片发送",
        False,
    ),
    "FanbookTencentWord": GsBoolConfig(
        "Fanbook登录链接用腾讯文档包装",
        "开启后将登录链接包装为 docs.qq.com 跳转链接，减少聊天平台拦截",
        False,
    ),
    "FanbookLoginForward": GsBoolConfig(
        "Fanbook登录消息使用合并转发",
        "开启后在支持的聊天平台通过合并转发发送登录链接",
        False,
    ),
}
