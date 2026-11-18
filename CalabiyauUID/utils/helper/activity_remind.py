"""卡拉彼丘活动结束 24 小时提醒的调度校准、去重与推送分发。"""

import asyncio
from datetime import datetime, timedelta

from gsuid_core.aps import scheduler
from gsuid_core.logger import logger
from gsuid_core.models import Event, Message
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.database.models import Subscribe

from .subscribe_common import (
    hours_until,
    get_all_subscribers,
    subscribe_scope_key,
    build_dispatch_messages as _build_dispatch_messages,
    dispatch_subscribe_text,
    is_user_subscribed_for_task,
    group_subscribers_for_dispatch as _group_subscribers_for_dispatch,
)
from ..api.biligame_wiki import (
    WikiError,
    WikiActivityItem,
    beijing_now,
    fetch_ongoing_activities,
)
from ..database.model_activity_remind import CalabiyauActivityRemind

SUBSCRIBE_TASK_NAME = "订阅卡丘国服活动结束"
REMIND_LEAD_TIME = timedelta(hours=24)
_REMIND_JOB_PREFIX = "klbq_activity_remind_"
_PRUNE_EXPIRED_SECONDS = 7 * 86400
_DISPATCH_HEADER = "[卡丘活动结束订阅]"
_LOG_TAG = "[卡拉彼丘·活动订阅]"

_sync_lock = asyncio.Lock()
_scheduled_items_by_end_ts: dict[int, list[WikiActivityItem]] = {}


async def get_all_activity_subscribers() -> list[Subscribe]:
    """读取全部活动结束订阅记录。"""
    return await get_all_subscribers(SUBSCRIBE_TASK_NAME)


async def is_user_subscribed(ev: Event) -> bool:
    """判断当前用户在当前会话是否已订阅活动结束提醒。"""
    return await is_user_subscribed_for_task(SUBSCRIBE_TASK_NAME, ev)


def build_reminder_body(items: list[WikiActivityItem], now: datetime) -> str:
    """按相同结束时间分组拼接活动结束提醒正文。"""
    grouped: dict[datetime, list[WikiActivityItem]] = {}
    for item in sorted(items, key=lambda entry: (entry.end_at, entry.title)):
        if item.end_at not in grouped:
            grouped[item.end_at] = []
        grouped[item.end_at].append(item)

    blocks: list[str] = []
    for end_at in sorted(grouped.keys()):
        group_items = grouped[end_at]
        hours_left = hours_until(end_at, now)
        lines = ["你订阅的以下活动："]
        lines.extend(f"· {item.title}" for item in group_items)
        lines.append(f"将于 {end_at.strftime('%Y-%m-%d %H:%M')} （剩余 {hours_left} 小时）结束，请确认游戏进度！")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_subscribe_receipt(already_ending: list[WikiActivityItem], now: datetime) -> str:
    """构建订阅成功回执；若当前已有不足 24h 的活动则顺带提示。"""
    base = "已为你开启卡拉彼丘活动结束提醒。"
    if not already_ending:
        return base
    ordered = sorted(already_ending, key=lambda entry: (entry.end_at, entry.title))
    lines = [base, "", "当前已有即将结束的活动（本次订阅不补推）："]
    for item in ordered:
        hours_left = hours_until(item.end_at, now)
        lines.append(f"· {item.title}（{item.end_at.strftime('%Y-%m-%d %H:%M')} 结束，剩余 {hours_left} 小时）")
    return "\n".join(lines)


def group_subscribers_for_dispatch(
    subscribers: list[Subscribe],
) -> list[tuple[Subscribe, list[str]]]:
    """同群多用户合并为一条消息并汇总需 @ 的用户列表，私聊不带 @。"""
    return _group_subscribers_for_dispatch(subscribers)


def build_dispatch_messages(body: str, at_user_ids: list[str]) -> list[Message]:
    """构建最终发送的消息段列表；私聊传入空列表即可省略 @。"""
    return _build_dispatch_messages(body, at_user_ids, header=_DISPATCH_HEADER)


async def dispatch_activity_reminders(
    items: list[WikiActivityItem],
    subscribers: list[Subscribe],
    now: datetime,
) -> bool:
    """向所有订阅会话发送活动结束提醒，成功至少一次返回 True。"""
    if not items or not subscribers:
        return False
    body = build_reminder_body(items, now)
    return await dispatch_subscribe_text(
        subscribers,
        header=_DISPATCH_HEADER,
        body=body,
        log_tag=_LOG_TAG,
    )


def _clear_reminder_jobs(keep_job_ids: set[str]) -> None:
    for job in scheduler.get_jobs():
        if job.id.startswith(_REMIND_JOB_PREFIX) and job.id not in keep_job_ids:
            scheduler.remove_job(job.id)


async def _execute_due_reminder_job(target_end_ts: int) -> None:
    now = beijing_now()
    subscribers = await get_all_activity_subscribers()
    if not subscribers:
        return
    try:
        activities = await fetch_ongoing_activities(now)
    except WikiError as exc:
        logger.warning(f"{_LOG_TAG} 到点复核 Wiki 失败，使用内存活动快照：{exc}")
        fallback_items = (
            _scheduled_items_by_end_ts[target_end_ts] if target_end_ts in _scheduled_items_by_end_ts else []
        )
        activities = fallback_items
    if not activities:
        return
    await sync_reminders_from_activities(activities, now, allow_catchup_send=True)


async def sync_reminders_from_activities(
    activities: list[WikiActivityItem],
    now: datetime,
    *,
    allow_catchup_send: bool = True,
) -> None:
    """校准内存 DateTrigger 定时任务，并补推未提醒且尚未结束的临期活动。"""
    async with _sync_lock:
        subscribers = await get_all_activity_subscribers()
        if not subscribers:
            _scheduled_items_by_end_ts.clear()
            _clear_reminder_jobs(set())
            return

        timed = [item for item in activities if not item.is_permanent and now < item.end_at]
        reminded_map = await CalabiyauActivityRemind.get_reminded_map()
        due_items: list[WikiActivityItem] = []
        future_by_end_ts: dict[int, list[WikiActivityItem]] = {}

        for item in timed:
            end_ts = int(item.end_at.timestamp())
            already_reminded = item.title in reminded_map and reminded_map[item.title] == end_ts
            if already_reminded:
                continue
            if item.end_at - now <= REMIND_LEAD_TIME:
                due_items.append(item)
            else:
                if end_ts not in future_by_end_ts:
                    future_by_end_ts[end_ts] = []
                future_by_end_ts[end_ts].append(item)

        if due_items and allow_catchup_send:
            sent = await dispatch_activity_reminders(due_items, subscribers, now)
            if sent:
                await CalabiyauActivityRemind.mark_reminded(
                    [(item.title, int(item.end_at.timestamp())) for item in due_items],
                    int(now.timestamp()),
                )

        _scheduled_items_by_end_ts.clear()
        desired_job_ids: set[str] = set()
        for end_ts, group_items in future_by_end_ts.items():
            _scheduled_items_by_end_ts[end_ts] = group_items
            remind_at = group_items[0].end_at - REMIND_LEAD_TIME
            job_id = f"{_REMIND_JOB_PREFIX}{end_ts}"
            desired_job_ids.add(job_id)
            scheduler.add_job(
                _execute_due_reminder_job,
                "date",
                run_date=remind_at,
                id=job_id,
                replace_existing=True,
                kwargs={"target_end_ts": end_ts},
            )

        _clear_reminder_jobs(desired_job_ids)
        await CalabiyauActivityRemind.prune_expired(int(now.timestamp()) - _PRUNE_EXPIRED_SECONDS)


async def sync_activity_reminders() -> None:
    """定时拉取进行中活动并同步 24 小时结束提醒。"""
    subscribers = await get_all_activity_subscribers()
    if not subscribers:
        return
    now = beijing_now()
    try:
        activities = await fetch_ongoing_activities(now)
    except WikiError as exc:
        logger.warning(f"{_LOG_TAG} 同步活动列表失败：{exc}")
        return
    await sync_reminders_from_activities(activities, now, allow_catchup_send=True)


async def subscribe_activity_reminder(ev: Event) -> str:
    """为用户开启当前会话的活动结束提醒，并顺带提示已有临期活动。"""
    if await is_user_subscribed(ev):
        return "你已订阅卡拉彼丘活动结束提醒，无需重复订阅。"

    existing_subscribers = await get_all_activity_subscribers()
    had_subscribers = bool(existing_subscribers)

    scope_key = subscribe_scope_key(ev)
    await gs_subscribe.add_subscribe(
        "single",
        SUBSCRIBE_TASK_NAME,
        ev,
        uid=scope_key,
    )

    now = beijing_now()
    try:
        activities = await fetch_ongoing_activities(now)
    except WikiError as exc:
        logger.warning(f"{_LOG_TAG} 订阅时拉取活动列表失败：{exc}")
        return build_subscribe_receipt([], now)

    already_ending = [
        item for item in activities if not item.is_permanent and timedelta(0) < (item.end_at - now) <= REMIND_LEAD_TIME
    ]
    # 首个订阅者开启前本就不足 24h 的活动仅在回执中提示，不触发历史补推
    if already_ending and not had_subscribers:
        await CalabiyauActivityRemind.mark_reminded(
            [(item.title, int(item.end_at.timestamp())) for item in already_ending],
            int(now.timestamp()),
        )

    await sync_reminders_from_activities(activities, now, allow_catchup_send=False)
    return build_subscribe_receipt(already_ending, now)


async def unsubscribe_activity_reminder(ev: Event) -> str:
    """取消当前用户在当前会话的活动结束提醒。"""
    if not await is_user_subscribed(ev):
        return "你尚未订阅卡拉彼丘活动结束提醒。"

    scope_key = subscribe_scope_key(ev)
    await gs_subscribe.delete_subscribe(
        "single",
        SUBSCRIBE_TASK_NAME,
        ev,
        uid=scope_key,
    )
    remaining = await get_all_activity_subscribers()
    if not remaining:
        _scheduled_items_by_end_ts.clear()
        _clear_reminder_jobs(set())
    return "已取消卡拉彼丘活动结束提醒。"
