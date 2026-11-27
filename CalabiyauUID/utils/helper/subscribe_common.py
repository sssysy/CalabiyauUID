"""订阅作用域、记录收窄与群聊合并分发公共逻辑。"""

import asyncio
from datetime import datetime
from collections.abc import Sequence

from gsuid_core.logger import logger
from gsuid_core.models import Event, Message
from gsuid_core.segment import MessageSegment
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.database.models import Subscribe

DEFAULT_SEND_INTERVAL_SECONDS = 1.5
SIGN_SUBSCRIBE_TASK_NAME = "订阅卡丘Fanbook签到"


def subscribe_scope_key(ev: Event) -> str:
    """区分群聊与私聊订阅作用域，避免同一用户在多群互覆。"""
    if ev.user_type == "group" and ev.group_id:
        return f"group:{ev.group_id}"
    return "direct"


def narrow_subscribe_rows(raw_rows: object) -> list[Subscribe]:
    """将框架无泛型注解的订阅查询结果收窄为 Subscribe 列表。"""
    if not isinstance(raw_rows, Sequence):
        return []
    return [row for row in raw_rows if isinstance(row, Subscribe)]


async def get_all_subscribers(task_name: str) -> list[Subscribe]:
    """读取指定任务名的全部订阅记录。"""
    raw_rows: object = await gs_subscribe.get_subscribe(task_name)
    return narrow_subscribe_rows(raw_rows)


async def is_user_subscribed_for_task(task_name: str, ev: Event) -> bool:
    """判断当前用户在当前会话是否已订阅指定任务。"""
    scope_key = subscribe_scope_key(ev)
    raw_rows: object = await gs_subscribe.get_subscribe(
        task_name,
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        user_type=ev.user_type,
        uid=scope_key,
    )
    rows = narrow_subscribe_rows(raw_rows)
    if ev.user_type == "group" and ev.group_id:
        return any(row.group_id == ev.group_id for row in rows)
    return bool(rows)


def hours_until(target_at: datetime, now: datetime) -> int:
    """计算距离目标时间点的取整小时数（最少 1 小时）。"""
    seconds = max(0.0, (target_at - now).total_seconds())
    return max(1, round(seconds / 3600))


def group_subscribers_for_dispatch(
    subscribers: list[Subscribe],
) -> list[tuple[Subscribe, list[str]]]:
    """同群多用户合并为一条消息并汇总需 @ 的用户列表，私聊不带 @。"""
    targets: list[tuple[Subscribe, list[str]]] = []
    group_index: dict[tuple[str, str, str], int] = {}
    direct_seen: set[tuple[str, str, str]] = set()

    for sub in subscribers:
        ws_id = sub.WS_BOT_ID if sub.WS_BOT_ID else ""
        if sub.user_type == "group" and sub.group_id:
            key = (ws_id, sub.bot_id, sub.group_id)
            if key not in group_index:
                group_index[key] = len(targets)
                user_ids = [sub.user_id] if sub.user_id else []
                targets.append((sub, user_ids))
            else:
                target_users = targets[group_index[key]][1]
                if sub.user_id and sub.user_id not in target_users:
                    target_users.append(sub.user_id)
        else:
            direct_key = (ws_id, sub.bot_id, sub.user_id)
            if direct_key not in direct_seen:
                direct_seen.add(direct_key)
                targets.append((sub, []))
    return targets


def build_dispatch_messages(
    body: str,
    at_user_ids: list[str],
    *,
    header: str,
) -> list[Message]:
    """构建最终发送的消息段列表；私聊传入空列表即可省略 @。"""
    segments: list[Message] = []
    for user_id in at_user_ids:
        segments.append(MessageSegment.at(user_id))
        segments.append(MessageSegment.text(" "))
    segments.append(MessageSegment.text(f"{header}\n{body}"))
    return segments


async def dispatch_subscribe_text(
    subscribers: list[Subscribe],
    *,
    header: str,
    body: str,
    log_tag: str,
    interval_seconds: float = DEFAULT_SEND_INTERVAL_SECONDS,
) -> bool:
    """向订阅会话批量发送提醒文本，至少成功一条返回 True。"""
    if not body or not subscribers:
        return False
    targets = group_subscribers_for_dispatch(subscribers)
    any_sent = False

    for index, (sub, at_user_ids) in enumerate(targets):
        if index > 0:
            await asyncio.sleep(interval_seconds)
        messages = build_dispatch_messages(body, at_user_ids, header=header)
        try:
            retcode = await sub.send(messages)
        except (OSError, RuntimeError, TimeoutError) as exc:
            logger.warning(f"{log_tag} 推送订阅消息失败（group={sub.group_id}, user={sub.user_id}）：{exc}")
            continue
        if retcode == 0:
            any_sent = True
    return any_sent
