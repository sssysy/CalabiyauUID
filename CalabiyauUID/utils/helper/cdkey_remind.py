"""卡拉彼丘兑换码新增与临期 24 小时提醒的调度校准、去重与推送分发。"""

import re
import asyncio
from datetime import datetime, timedelta

from gsuid_core.aps import scheduler
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.database.models import Subscribe

from .subscribe_common import (
    hours_until,
    get_all_subscribers,
    subscribe_scope_key,
    dispatch_subscribe_text,
    is_user_subscribed_for_task,
)
from ..api.biligame_wiki import (
    WikiError,
    WikiRedeemCodeItem,
    beijing_now,
    fetch_active_redeem_codes,
)
from ..database.model_cdkey_remind import CalabiyauCdkeyRemind

SUBSCRIBE_TASK_NAME = "订阅卡丘国服兑换码"
REMIND_LEAD_TIME = timedelta(hours=24)
_REMIND_JOB_PREFIX = "klbq_cdkey_remind_"
_PRUNE_EXPIRED_SECONDS = 7 * 86400
_DISPATCH_HEADER = "[卡丘兑换码订阅]"
_LOG_TAG = "[卡拉彼丘·兑换码订阅]"
_REWARD_SPLIT_RE = re.compile(r"[,，]\s*")

_sync_lock = asyncio.Lock()
_scheduled_codes_by_end_ts: dict[int, list[WikiRedeemCodeItem]] = {}


def format_redeem_rewards(raw_rewards: str) -> str:
    """将 Wiki 奖励内容字符串格式化为 `道具 x 数量` 列表。"""
    cleaned = raw_rewards.strip()
    if not cleaned:
        return "未知"

    formatted: list[str] = []
    for segment in _REWARD_SPLIT_RE.split(cleaned):
        part = segment.strip()
        if not part:
            continue
        if "*" in part:
            name, quantity = part.split("*", 1)
            item_name = name.strip()
            item_quantity = quantity.strip() or "1"
        else:
            item_name = part
            item_quantity = "1"
        if item_name:
            formatted.append(f"{item_name} x {item_quantity}")
    return ", ".join(formatted) if formatted else "未知"


async def get_all_cdkey_subscribers() -> list[Subscribe]:
    """读取全部兑换码订阅记录。"""
    return await get_all_subscribers(SUBSCRIBE_TASK_NAME)


async def is_user_cdkey_subscribed(ev: Event) -> bool:
    """判断当前用户在当前会话是否已订阅兑换码提醒。"""
    return await is_user_subscribed_for_task(SUBSCRIBE_TASK_NAME, ev)


def build_new_cdkey_body(items: list[WikiRedeemCodeItem]) -> str:
    """构建新上线兑换码推送正文。"""
    ordered = sorted(items, key=lambda entry: (entry.is_permanent, entry.expires_at, entry.code))
    lines: list[str] = ["发现新的卡拉彼丘兑换码："]
    for item in ordered:
        expiry_text = "常驻" if item.is_permanent else item.expires_at.strftime("%Y-%m-%d %H:%M")
        rewards_text = format_redeem_rewards(item.rewards)
        lines.append(f"· 【{item.code}】有效期至：{expiry_text}")
        lines.append(f"    内含：{rewards_text}")
    return "\n".join(lines)


def build_expiring_cdkey_body(items: list[WikiRedeemCodeItem], now: datetime) -> str:
    """按相同失效时间分组拼接兑换码临期提醒正文。"""
    grouped: dict[datetime, list[WikiRedeemCodeItem]] = {}
    for item in sorted(items, key=lambda entry: (entry.expires_at, entry.code)):
        if item.expires_at not in grouped:
            grouped[item.expires_at] = []
        grouped[item.expires_at].append(item)

    blocks: list[str] = []
    for expires_at in sorted(grouped.keys()):
        group_items = grouped[expires_at]
        hours_left = hours_until(expires_at, now)
        lines = ["你订阅的以下兑换码："]
        for item in group_items:
            rewards_text = format_redeem_rewards(item.rewards)
            lines.append(f"· 【{item.code}】（内含：{rewards_text}）")
        lines.append(f"将于 {expires_at.strftime('%Y-%m-%d %H:%M')} （剩余 {hours_left} 小时）失效，请及时兑换！")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_cdkey_subscribe_receipt(items: list[WikiRedeemCodeItem]) -> str:
    """构建兑换码订阅成功回执；若当前有可用兑换码则一并列出。"""
    base = "已为你开启卡拉彼丘兑换码订阅。"
    if not items:
        return base
    ordered = sorted(items, key=lambda entry: (entry.is_permanent, entry.expires_at, entry.code))
    lines = [base, "", "当前可用兑换码（本次订阅不重复推送）："]
    for item in ordered:
        expiry_text = "常驻" if item.is_permanent else item.expires_at.strftime("%Y-%m-%d %H:%M")
        rewards_text = format_redeem_rewards(item.rewards)
        lines.append(f"· 【{item.code}】有效期至：{expiry_text}")
        lines.append(f"    内含：{rewards_text}")
    return "\n".join(lines)


async def dispatch_new_cdkey_reminders(
    items: list[WikiRedeemCodeItem],
    subscribers: list[Subscribe],
) -> bool:
    """向所有订阅会话发送新兑换码通知，至少成功一条返回 True。"""
    if not items or not subscribers:
        return False
    body = build_new_cdkey_body(items)
    return await dispatch_subscribe_text(
        subscribers,
        header=_DISPATCH_HEADER,
        body=body,
        log_tag=_LOG_TAG,
    )


async def dispatch_expiring_cdkey_reminders(
    items: list[WikiRedeemCodeItem],
    subscribers: list[Subscribe],
    now: datetime,
) -> bool:
    """向所有订阅会话发送兑换码临期提醒，至少成功一条返回 True。"""
    if not items or not subscribers:
        return False
    body = build_expiring_cdkey_body(items, now)
    return await dispatch_subscribe_text(
        subscribers,
        header=_DISPATCH_HEADER,
        body=body,
        log_tag=_LOG_TAG,
    )


def _clear_cdkey_jobs(keep_job_ids: set[str]) -> None:
    for job in scheduler.get_jobs():
        if job.id.startswith(_REMIND_JOB_PREFIX) and job.id not in keep_job_ids:
            scheduler.remove_job(job.id)


async def _execute_due_cdkey_job(target_end_ts: int) -> None:
    now = beijing_now()
    subscribers = await get_all_cdkey_subscribers()
    if not subscribers:
        return
    try:
        codes = await fetch_active_redeem_codes(now)
    except WikiError as exc:
        logger.warning(f"{_LOG_TAG} 到点复核 Wiki 失败，使用内存兑换码快照：{exc}")
        codes = _scheduled_codes_by_end_ts[target_end_ts] if target_end_ts in _scheduled_codes_by_end_ts else []
    if not codes:
        return
    await sync_cdkey_reminders_from_codes(codes, now, allow_catchup_send=True)


async def sync_cdkey_reminders_from_codes(
    codes: list[WikiRedeemCodeItem],
    now: datetime,
    *,
    allow_catchup_send: bool = True,
) -> None:
    """同步新上线兑换码通知、24 小时临期 DateTrigger 任务与漏推补发。"""
    async with _sync_lock:
        subscribers = await get_all_cdkey_subscribers()
        if not subscribers:
            _scheduled_codes_by_end_ts.clear()
            _clear_cdkey_jobs(set())
            return

        active = [item for item in codes if item.is_permanent or now < item.expires_at]
        state_map = await CalabiyauCdkeyRemind.get_state_map()

        new_items = [item for item in active if item.code not in state_map or not state_map[item.code].new_notified]
        new_codes = {item.code for item in new_items}

        due_expiring_items: list[WikiRedeemCodeItem] = []
        future_by_end_ts: dict[int, list[WikiRedeemCodeItem]] = {}
        for item in active:
            if item.is_permanent:
                continue
            end_ts = int(item.expires_at.timestamp())
            already_expiring = (
                item.code in state_map
                and state_map[item.code].expiring_notified
                and state_map[item.code].expires_at_ts == end_ts
            )
            if already_expiring:
                continue
            if item.expires_at - now <= REMIND_LEAD_TIME:
                # 同周期刚作为新码推送时已包含有效期，避免连续两条刷屏
                if item.code not in new_codes:
                    due_expiring_items.append(item)
            else:
                if end_ts not in future_by_end_ts:
                    future_by_end_ts[end_ts] = []
                future_by_end_ts[end_ts].append(item)

        now_ts = int(now.timestamp())
        if allow_catchup_send and new_items:
            sent_new = await dispatch_new_cdkey_reminders(new_items, subscribers)
            if sent_new:
                await CalabiyauCdkeyRemind.mark_new_notified(
                    [(item.code, int(item.expires_at.timestamp()), item.is_permanent) for item in new_items],
                    now_ts,
                )
                new_already_due = [
                    item for item in new_items if not item.is_permanent and item.expires_at - now <= REMIND_LEAD_TIME
                ]
                if new_already_due:
                    await CalabiyauCdkeyRemind.mark_expiring_notified(
                        [(item.code, int(item.expires_at.timestamp()), item.is_permanent) for item in new_already_due],
                        now_ts,
                    )

        if allow_catchup_send and due_expiring_items:
            sent_expiring = await dispatch_expiring_cdkey_reminders(due_expiring_items, subscribers, now)
            if sent_expiring:
                await CalabiyauCdkeyRemind.mark_expiring_notified(
                    [(item.code, int(item.expires_at.timestamp()), item.is_permanent) for item in due_expiring_items],
                    now_ts,
                )

        _scheduled_codes_by_end_ts.clear()
        desired_job_ids: set[str] = set()
        for end_ts, group_items in future_by_end_ts.items():
            _scheduled_codes_by_end_ts[end_ts] = group_items
            remind_at = group_items[0].expires_at - REMIND_LEAD_TIME
            job_id = f"{_REMIND_JOB_PREFIX}{end_ts}"
            desired_job_ids.add(job_id)
            scheduler.add_job(
                _execute_due_cdkey_job,
                "date",
                run_date=remind_at,
                id=job_id,
                replace_existing=True,
                kwargs={"target_end_ts": end_ts},
            )

        _clear_cdkey_jobs(desired_job_ids)
        await CalabiyauCdkeyRemind.prune_expired(now_ts - _PRUNE_EXPIRED_SECONDS)


async def sync_cdkey_reminders() -> None:
    """定时拉取可用兑换码并同步新码推送与 24 小时临期提醒。"""
    subscribers = await get_all_cdkey_subscribers()
    if not subscribers:
        return
    now = beijing_now()
    try:
        codes = await fetch_active_redeem_codes(now)
    except WikiError as exc:
        logger.warning(f"{_LOG_TAG} 同步兑换码列表失败：{exc}")
        return
    await sync_cdkey_reminders_from_codes(codes, now, allow_catchup_send=True)


async def subscribe_cdkey_reminder(ev: Event) -> str:
    """为用户开启当前会话的兑换码订阅，并列出当前可用兑换码。"""
    if await is_user_cdkey_subscribed(ev):
        return "你已订阅卡拉彼丘兑换码提醒，无需重复订阅。"

    existing_subscribers = await get_all_cdkey_subscribers()
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
        codes = await fetch_active_redeem_codes(now)
    except WikiError as exc:
        logger.warning(f"{_LOG_TAG} 订阅时拉取兑换码列表失败：{exc}")
        return build_cdkey_subscribe_receipt([])

    # 首个订阅者开启前本就存在的兑换码仅在回执中展示，不触发历史补推
    if not had_subscribers and codes:
        now_ts = int(now.timestamp())
        await CalabiyauCdkeyRemind.mark_new_notified(
            [(item.code, int(item.expires_at.timestamp()), item.is_permanent) for item in codes],
            now_ts,
        )
        already_expiring = [
            item
            for item in codes
            if not item.is_permanent and timedelta(0) < (item.expires_at - now) <= REMIND_LEAD_TIME
        ]
        if already_expiring:
            await CalabiyauCdkeyRemind.mark_expiring_notified(
                [(item.code, int(item.expires_at.timestamp()), item.is_permanent) for item in already_expiring],
                now_ts,
            )

    await sync_cdkey_reminders_from_codes(codes, now, allow_catchup_send=False)
    return build_cdkey_subscribe_receipt(codes)


async def unsubscribe_cdkey_reminder(ev: Event) -> str:
    """取消当前用户在当前会话的兑换码订阅。"""
    if not await is_user_cdkey_subscribed(ev):
        return "你尚未订阅卡拉彼丘兑换码提醒。"

    scope_key = subscribe_scope_key(ev)
    await gs_subscribe.delete_subscribe(
        "single",
        SUBSCRIBE_TASK_NAME,
        ev,
        uid=scope_key,
    )
    remaining = await get_all_cdkey_subscribers()
    if not remaining:
        _scheduled_codes_by_end_ts.clear()
        _clear_cdkey_jobs(set())
    return "已取消卡拉彼丘兑换码提醒。"
