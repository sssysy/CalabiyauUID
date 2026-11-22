from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsIntConfig,
    GsStrConfig,
    GsBoolConfig,
    GsImageConfig,
    GsTimeRConfig,
    GsListStrConfig,
)

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
        "卡丘 Fanbook 登录页面URL",
        "登录页对外访问地址，留空自动探测",
        "",
    ),
    "FanbookSignDaily": GsBoolConfig(
        "开启Fanbook每日自动签到",
        "定时自动签到总开关，关闭后不会执行每日定时签到任务",
        True,
    ),
    "FanbookSignAll": GsBoolConfig(
        "定时签全员",
        "开启后定时任务会对所有已登录Fanbook的账号签到",
        False,
    ),
    "FanbookSignTime": GsTimeRConfig(
        "Fanbook每日签到时间",
        "每天自动签到时间（时, 分），修改后重启生效",
        (8, 0),
    ),
    "FanbookSignDelayRange": GsListStrConfig(
        "签到延迟",
        "定时签到随机延迟区间（秒），依次填写最小和最大延迟",
        ["5", "10"],
    ),
    "FanbookSignConcurrency": GsIntConfig(
        "自动签到并发数",
        "每日定时签到最大并发账号数，最大 20",
        3,
        max_value=20,
    ),
    "FanbookSignPushGroup": GsBoolConfig(
        "自动签到群聊推送",
        "在群聊内开启自动签到时，每日签到完成后向对应群推送汇总消息",
        True,
    ),
    "FanbookSignPushPrivate": GsBoolConfig(
        "自动签到私聊推送",
        "在私聊内开启自动签到时，每日签到完成后向对应私聊推送详细结果",
        True,
    ),
}
