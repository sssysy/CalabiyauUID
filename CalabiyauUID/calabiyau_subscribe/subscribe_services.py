"""活动结束提醒订阅服务与定时校准入口。"""

from datetime import timedelta

from gsuid_core.aps import scheduler
from gsuid_core.models import Event

from ..utils.api.biligame_wiki import beijing_now
from ..utils.helper.activity_remind import (
    sync_activity_reminders,
    subscribe_activity_reminder,
    unsubscribe_activity_reminder,
)

_STARTUP_JOB_ID = "klbq_activity_remind_startup"
_STARTUP_DELAY = timedelta(seconds=30)


async def handle_subscribe_activity(ev: Event) -> str:
    """处理开启活动结束提醒命令。"""
    return await subscribe_activity_reminder(ev)


async def handle_unsubscribe_activity(ev: Event) -> str:
    """处理取消活动结束提醒命令。"""
    return await unsubscribe_activity_reminder(ev)


async def run_activity_remind_sync() -> None:
    """执行一次活动结束提醒同步与漏推校准。"""
    await sync_activity_reminders()


def schedule_startup_activity_sync() -> None:
    """Core 启动后延迟 30 秒做一次漏推检查与调度校准，等待连接就绪。"""
    scheduler.add_job(
        sync_activity_reminders,
        "date",
        run_date=beijing_now() + _STARTUP_DELAY,
        id=_STARTUP_JOB_ID,
        replace_existing=True,
    )
