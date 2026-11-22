"""Fanbook 每日签到业务编排、自动签到开关与批量推送。"""

from __future__ import annotations

import time
import random
import asyncio
from datetime import datetime, timezone, timedelta
from dataclasses import field, dataclass

from gsuid_core.aps import scheduler
from gsuid_core.logger import logger
from gsuid_core.models import Event, Message
from gsuid_core.segment import MessageSegment
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.database.models import Subscribe

from ..calabiyau_config import CalabiyauConfig
from ..utils.api.fanbook_sign import (
    FanbookSignError,
    FanbookSignResult,
    beijing_today_str,
    query_shop_points,
    perform_daily_sign,
)
from ..utils.database.model_fanbook import CalabiyauFanbookUser
from ..utils.helper.subscribe_common import (
    DEFAULT_SEND_INTERVAL_SECONDS,
    get_all_subscribers,
    subscribe_scope_key,
    is_user_subscribed_for_task,
)
from ..utils.database.model_fanbook_sign import CalabiyauFanbookSign
from ..utils.render.html.renderer.fanbook_auto_sign_card import (
    AutoSignFailureItem,
    render_auto_sign_card,
)

SIGN_SUBSCRIBE_TASK_NAME = "订阅卡丘Fanbook签到"
_LOG_TAG = "[卡拉彼丘·Fanbook签到]"
_BEIJING_TZ = timezone(timedelta(hours=8))
_REVOKED_EXPIRE_TS = 1
_DEFAULT_SIGN_HOUR = 0
_DEFAULT_SIGN_MINUTE = 5
_STARTUP_SIGN_JOB_ID = "klbq_fanbook_sign_startup"
_STARTUP_SIGN_DELAY = timedelta(seconds=45)

_batch_sign_lock = asyncio.Lock()


@dataclass(frozen=True, slots=True)
class UserSignReport:
    """单用户的批量签到执行结果。"""

    bot_id: str
    user_id: str
    success: bool
    text: str
    failure_label: str = ""
    error_reason: str = ""


@dataclass(slots=True)
class _GroupPushBucket:
    sub: Subscribe
    success_count: int = 0
    failed_count: int = 0
    failures: list[AutoSignFailureItem] = field(default_factory=list)

    def add(self, report: UserSignReport) -> None:
        if report.success:
            self.success_count += 1
        else:
            self.failed_count += 1
            if report.failure_label:
                self.failures.append(
                    AutoSignFailureItem(
                        label=report.failure_label,
                        reason=report.error_reason if report.error_reason else "未知错误",
                    )
                )


def _get_bool_config(key: str) -> bool:
    value: object = CalabiyauConfig.get_config(key).data
    return value is True


def _get_int_config(key: str, *, default: int, minimum: int, maximum: int) -> int:
    value: object = CalabiyauConfig.get_config(key).data
    if isinstance(value, int) and not isinstance(value, bool):
        return max(minimum, min(maximum, value))
    return default


def _parse_delay_range() -> tuple[int, int]:
    raw: object = CalabiyauConfig.get_config("FanbookSignDelayRange").data
    if not isinstance(raw, list) or len(raw) < 2:
        return 0, 90
    first = raw[0].strip() if isinstance(raw[0], str) else str(raw[0]).strip()
    second = raw[1].strip() if isinstance(raw[1], str) else str(raw[1]).strip()
    if not first.isdigit() or not second.isdigit():
        return 0, 90
    min_delay = max(0, min(600, int(first)))
    max_delay = max(0, min(600, int(second)))
    if min_delay > max_delay:
        min_delay, max_delay = max_delay, min_delay
    return min_delay, max_delay


def parse_sign_time() -> tuple[int, int]:
    """解析控制台配置的每日签到时间（时, 分）。"""
    raw: object = CalabiyauConfig.get_config("FanbookSignTime").data
    if isinstance(raw, (tuple, list)) and len(raw) >= 2:
        raw_hour = raw[0]
        raw_minute = raw[1]
        if (
            isinstance(raw_hour, int)
            and not isinstance(raw_hour, bool)
            and isinstance(raw_minute, int)
            and not isinstance(raw_minute, bool)
            and 0 <= raw_hour <= 23
            and 0 <= raw_minute <= 59
        ):
            return raw_hour, raw_minute
    if isinstance(raw, str) and ":" in raw:
        parts = raw.split(":", maxsplit=1)
        if parts[0].strip().isdigit() and parts[1].strip().isdigit():
            hour = int(parts[0].strip())
            minute = int(parts[1].strip())
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute
    return _DEFAULT_SIGN_HOUR, _DEFAULT_SIGN_MINUTE


def _format_account_name(account: CalabiyauFanbookUser) -> str:
    if account.nickname:
        return account.nickname
    return account.fb_short_id if account.fb_short_id else account.fb_user_id


def _format_failure_label(account: CalabiyauFanbookUser) -> str:
    display_id = account.fb_short_id if account.fb_short_id else account.fb_user_id
    if account.nickname and display_id and account.nickname != display_id:
        return f"{account.nickname}({display_id})"
    return account.nickname if account.nickname else display_id


def _format_sign_result(account: CalabiyauFanbookUser, result: FanbookSignResult) -> str:
    status_line = "ℹ️ 今日已完成签到！" if result.already_signed else "✅ 签到成功！"
    delta_label = "今日" if result.already_signed else "本次"
    lines = [
        "[卡拉彼丘社区签到]",
        status_line,
        f"账号：{_format_account_name(account)}",
        f"总积分：{result.shop_point} ({delta_label}+{result.score})",
        f"今日排名：第 {result.rank} 位" if result.rank > 0 else "今日排名：暂无",
        "",
        f"连续签到：{result.continuous_sign_days} 天",
        f"累计签到：{result.sum_sign_days} 天",
    ]
    return "\n".join(lines)


def _is_account_expired(account: CalabiyauFanbookUser, now_ts: int) -> bool:
    if account.expire_at_ts == _REVOKED_EXPIRE_TS:
        return True
    return account.expire_at_ts > 0 and account.expire_at_ts <= now_ts


async def _get_active_fanbook_account(
    bot_id: str,
    user_id: str,
    *,
    header: str,
) -> tuple[CalabiyauFanbookUser | None, str]:
    account = await CalabiyauFanbookUser.get_account(bot_id, user_id)
    if account is None or not account.sign:
        return None, f"{header}\n⚠️ 尚未登录 Fanbook\n请先发送 kq登录 完成登录。"
    if _is_account_expired(account, int(time.time())):
        return (
            None,
            f"{header}\n⚠️ Fanbook 登录凭证已过期\n账号：{_format_account_name(account)}\n请发送 kq登录 重新登录。",
        )
    return account, ""


async def _execute_sign_for_account(account: CalabiyauFanbookUser, today_str: str) -> UserSignReport:
    try:
        result = await perform_daily_sign(
            fb_user_id=account.fb_user_id,
            fb_short_id=account.fb_short_id,
            sign_token=account.sign,
        )
    except FanbookSignError as exc:
        error_msg = f"签到失败：{exc}"
        await CalabiyauFanbookSign.record_outcome(
            bot_id=account.bot_id,
            user_id=account.user_id,
            sign_date=today_str,
            status="failed",
            msg=error_msg,
        )
        return UserSignReport(
            bot_id=account.bot_id,
            user_id=account.user_id,
            success=False,
            text=(f"[卡拉彼丘社区签到]\n❌ 签到失败！\n账号：{_format_account_name(account)}\n原因：{exc}"),
            failure_label=_format_failure_label(account),
            error_reason=str(exc),
        )

    message = _format_sign_result(account, result)
    summary = f"+{result.score}积分（总{result.shop_point}）" if result.score > 0 else "签到成功"
    await CalabiyauFanbookSign.record_outcome(
        bot_id=account.bot_id,
        user_id=account.user_id,
        sign_date=today_str,
        status="ok",
        msg=summary,
        total_days=result.sum_sign_days,
        continuous_days=result.continuous_sign_days,
        shop_point=result.shop_point,
    )
    return UserSignReport(
        bot_id=account.bot_id,
        user_id=account.user_id,
        success=True,
        text=message,
    )


async def run_manual_fanbook_sign(bot_id: str, user_id: str) -> str:
    """执行单用户的手动 Fanbook 签到并返回展示文案。"""
    account, error_reply = await _get_active_fanbook_account(bot_id, user_id, header="[卡拉彼丘社区签到]")
    if account is None:
        return error_reply

    report = await _execute_sign_for_account(account, beijing_today_str())
    return report.text


async def query_fanbook_points(bot_id: str, user_id: str) -> str:
    """查询当前用户的卡拉彼丘 Fanbook 社区总积分。"""
    header = "[卡丘社区积分]"
    account, error_reply = await _get_active_fanbook_account(bot_id, user_id, header=header)
    if account is None:
        return error_reply

    account_name = _format_account_name(account)
    try:
        points = await query_shop_points(
            fb_user_id=account.fb_user_id,
            sign_token=account.sign,
        )
    except FanbookSignError as exc:
        return f"{header}\n❌ 查询失败！\n账号：{account_name}\n原因：{exc}"

    return "\n".join(
        [
            header,
            f"账号：{account_name}",
            f"总积分：{points}",
        ]
    )


async def enable_auto_sign(ev: Event) -> str:
    """开启当前用户的 Fanbook 自动签到并绑定当前会话推送。"""
    account, error_reply = await _get_active_fanbook_account(ev.bot_id, ev.user_id, header="[卡拉彼丘社区签到]")
    if account is None:
        return error_reply

    await CalabiyauFanbookSign.set_auto_sign(ev.bot_id, ev.user_id, enabled=True)
    if not await is_user_subscribed_for_task(SIGN_SUBSCRIBE_TASK_NAME, ev):
        await gs_subscribe.add_subscribe(
            "single",
            SIGN_SUBSCRIBE_TASK_NAME,
            ev,
            uid=subscribe_scope_key(ev),
        )

    return "✅ 已开启每日自动签到！"


async def disable_auto_sign(ev: Event) -> str:
    """关闭当前用户的 Fanbook 自动签到并移除本会话推送订阅。"""
    await CalabiyauFanbookSign.set_auto_sign(ev.bot_id, ev.user_id, enabled=False)
    if await is_user_subscribed_for_task(SIGN_SUBSCRIBE_TASK_NAME, ev):
        await gs_subscribe.delete_subscribe(
            "single",
            SIGN_SUBSCRIBE_TASK_NAME,
            ev,
            uid=subscribe_scope_key(ev),
        )
    return "✅ 已关闭每日自动签到"


async def _push_sign_reports(
    reports: list[UserSignReport],
    sign_date: str,
    *,
    skip_group_id: str | None = None,
) -> None:
    if not reports:
        return
    push_private = _get_bool_config("FanbookSignPushPrivate")
    push_group = _get_bool_config("FanbookSignPushGroup")
    if not push_private and not push_group:
        return

    report_by_user: dict[tuple[str, str], UserSignReport] = {
        (report.bot_id, report.user_id): report for report in reports
    }
    subscribers = await get_all_subscribers(SIGN_SUBSCRIBE_TASK_NAME)
    group_buckets: dict[tuple[str, str, str, str], _GroupPushBucket] = {}
    sent_count = 0

    for sub in subscribers:
        key = (sub.bot_id, sub.user_id)
        if key not in report_by_user:
            continue
        report = report_by_user[key]
        if sub.user_type == "group" and sub.group_id:
            if not push_group:
                continue
            ws_id = sub.WS_BOT_ID if sub.WS_BOT_ID else ""
            group_key = (ws_id, sub.bot_id, sub.group_id, sub.bot_self_id)
            if group_key not in group_buckets:
                group_buckets[group_key] = _GroupPushBucket(sub=sub)
            group_buckets[group_key].add(report)
            continue

        if not push_private:
            continue
        if sent_count > 0:
            await asyncio.sleep(DEFAULT_SEND_INTERVAL_SECONDS)
        try:
            await sub.send([MessageSegment.text(report.text)])
            sent_count += 1
        except (OSError, RuntimeError, TimeoutError) as exc:
            logger.warning(f"{_LOG_TAG} 私聊推送 user_id={sub.user_id} 失败：{exc}")

    for bucket in group_buckets.values():
        if bucket.success_count == 0 and bucket.failed_count == 0:
            continue
        if skip_group_id and bucket.sub.group_id == skip_group_id:
            continue
        if sent_count > 0:
            await asyncio.sleep(DEFAULT_SEND_INTERVAL_SECONDS)
        try:
            img_bytes = await render_auto_sign_card(
                sign_date=sign_date,
                success_count=bucket.success_count,
                failed_count=bucket.failed_count,
                failures=tuple(bucket.failures),
            )
            await bucket.sub.send([MessageSegment.image(img_bytes)])
            sent_count += 1
            continue
        except (OSError, RuntimeError) as exc:
            logger.warning(f"{_LOG_TAG} 群签到卡片渲染失败，回退文本推送：{exc}")

        lines = [
            f"[卡丘] 自动签到（{sign_date}）",
            "今日签到任务已完成！",
            f"签到成功：{bucket.success_count} 人",
            f"签到失败：{bucket.failed_count} 人",
        ]
        lines.extend(f"- {item.label}: {item.reason}" for item in bucket.failures)
        try:
            await bucket.sub.send([MessageSegment.text("\n".join(lines))])
            sent_count += 1
        except (OSError, RuntimeError, TimeoutError) as exc:
            logger.warning(f"{_LOG_TAG} 群推送 group_id={bucket.sub.group_id} 失败：{exc}")


async def run_all_fanbook_sign(ev: Event) -> list[Message] | str:
    """手动执行一次全部已登录 Fanbook 账号的签到任务。"""
    if _batch_sign_lock.locked():
        return "[卡丘] 当前已有签到任务正在执行，请稍后再试。"

    async with _batch_sign_lock:
        accounts = await CalabiyauFanbookUser.list_accounts()
        now_ts = int(time.time())
        targets = [account for account in accounts if account.sign and not _is_account_expired(account, now_ts)]
        if not targets:
            return "当前暂无有效的已登录 Fanbook 账号。"

        today_str = beijing_today_str()
        concurrency = _get_int_config("FanbookSignConcurrency", default=5, minimum=1, maximum=20)
        semaphore = asyncio.Semaphore(concurrency)

        async def _sign_one(target: CalabiyauFanbookUser) -> UserSignReport:
            async with semaphore:
                return await _execute_sign_for_account(target, today_str)

        reports = list(await asyncio.gather(*(_sign_one(target) for target in targets)))
        failures = tuple(
            AutoSignFailureItem(
                label=report.failure_label,
                reason=report.error_reason if report.error_reason else "未知错误",
            )
            for report in reports
            if not report.success and report.failure_label
        )
        ok_count = sum(1 for report in reports if report.success)
        fail_count = len(reports) - ok_count
        logger.info(f"{_LOG_TAG} 手动全部签到完成：总计 {len(reports)} 个，成功 {ok_count}，失败 {fail_count}")

        skip_group_id = ev.group_id if ev.user_type == "group" and ev.group_id else None
        await _push_sign_reports(reports, today_str, skip_group_id=skip_group_id)

        try:
            img_bytes = await render_auto_sign_card(
                sign_date=today_str,
                success_count=ok_count,
                failed_count=fail_count,
                failures=failures,
            )
            return [MessageSegment.image(img_bytes)]
        except (OSError, RuntimeError) as exc:
            logger.warning(f"{_LOG_TAG} 全部签到卡片渲染失败，回退文本：{exc}")
            lines = [
                f"[卡丘] 自动签到（{today_str}）",
                "今日签到任务已完成！",
                f"签到成功：{ok_count} 人",
                f"签到失败：{fail_count} 人",
            ]
            lines.extend(f"- {item.label}: {item.reason}" for item in failures)
            return "\n".join(lines)


async def run_scheduled_fanbook_sign(*, apply_jitter: bool = True) -> None:
    """执行每日 Fanbook 自动签到批量任务。"""
    if not _get_bool_config("FanbookSignDaily"):
        logger.info(f"{_LOG_TAG} 后台每日签到总开关已关闭，跳过本轮定时任务")
        return

    async with _batch_sign_lock:
        if apply_jitter:
            min_delay, max_delay = _parse_delay_range()
            if max_delay > 0:
                await asyncio.sleep(random.randint(min_delay, max_delay))

        accounts = await CalabiyauFanbookUser.list_accounts()
        if not accounts:
            return

        today_str = beijing_today_str()
        now_ts = int(time.time())
        sign_all = _get_bool_config("FanbookSignAll")
        auto_keys = set() if sign_all else await CalabiyauFanbookSign.list_auto_sign_keys()
        signed_today = await CalabiyauFanbookSign.list_signed_today_keys(today_str)

        targets: list[CalabiyauFanbookUser] = []
        for account in accounts:
            if not account.sign or _is_account_expired(account, now_ts):
                continue
            user_key = (account.bot_id, account.user_id)
            if not sign_all and user_key not in auto_keys:
                continue
            if user_key in signed_today:
                continue
            targets.append(account)

        if not targets:
            logger.info(f"{_LOG_TAG} 本轮无待签到的 Fanbook 账号")
            return

        concurrency = _get_int_config("FanbookSignConcurrency", default=5, minimum=1, maximum=20)
        semaphore = asyncio.Semaphore(concurrency)

        async def _sign_one(target: CalabiyauFanbookUser) -> UserSignReport:
            async with semaphore:
                return await _execute_sign_for_account(target, today_str)

        reports = list(await asyncio.gather(*(_sign_one(target) for target in targets)))
        ok_count = sum(1 for report in reports if report.success)
        fail_count = len(reports) - ok_count
        logger.info(f"{_LOG_TAG} 定时签到完成：总计 {len(reports)} 个，成功 {ok_count}，失败 {fail_count}")
        await _push_sign_reports(reports, today_str)


async def run_startup_catchup_sign() -> None:
    """Core 启动后若已过当日设定签到时间，为今日尚未签到的账号补签。"""
    if not _get_bool_config("FanbookSignDaily"):
        return
    now_bj = datetime.now(_BEIJING_TZ)
    sign_hour, sign_minute = parse_sign_time()
    if (now_bj.hour, now_bj.minute) < (sign_hour, sign_minute):
        return
    await run_scheduled_fanbook_sign(apply_jitter=False)


def schedule_startup_fanbook_sign() -> None:
    """Core 启动后延迟 45 秒检查当日是否漏签。"""
    scheduler.add_job(
        run_startup_catchup_sign,
        "date",
        run_date=datetime.now(_BEIJING_TZ) + _STARTUP_SIGN_DELAY,
        id=_STARTUP_SIGN_JOB_ID,
        replace_existing=True,
    )
