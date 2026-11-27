"""Fanbook 登录凭据按需续期、手动刷新与失效标记。"""

from __future__ import annotations

import time
import uuid
import asyncio
from typing import Literal
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

from gsuid_core.logger import logger

from ..api.fanbook import FanbookError, FanbookRefreshResult, refresh_token
from ..database.model_fanbook import CalabiyauFanbookUser

_LOG_TAG = "[卡拉彼丘·Fanbook登录]"
_BEIJING_TZ = timezone(timedelta(hours=8))
REVOKED_EXPIRE_TS = 1
REFRESH_THRESHOLD_S = 15 * 24 * 3600

_refresh_inflight: dict[tuple[str, str], asyncio.Future[FanbookRefreshResult]] = {}


@dataclass(frozen=True, slots=True)
class FanbookAccountCheckResult:
    """业务使用前对 Fanbook 凭据的检查与按需续期结果。"""

    status: Literal["ok", "not_logged_in", "expired"]
    account: CalabiyauFanbookUser | None = None


@dataclass(frozen=True, slots=True)
class FanbookManualRefreshResult:
    """用户手动触发 kq刷新令牌 的执行结果。"""

    success: bool
    message: str


def _consume_future_exception(fut: asyncio.Future[FanbookRefreshResult]) -> None:
    if not fut.cancelled():
        fut.exception()


def format_fanbook_account_name(account: CalabiyauFanbookUser) -> str:
    """返回适合展示给用户的 Fanbook 账号名称。"""
    if account.nickname:
        return account.nickname
    return account.fb_short_id if account.fb_short_id else account.fb_user_id


def is_fanbook_account_expired(account: CalabiyauFanbookUser, now_ts: int | None = None) -> bool:
    """判断本地保存的 Fanbook 凭据是否已失效或过期。"""
    if account.expire_at_ts == REVOKED_EXPIRE_TS:
        return True
    current_ts = now_ts if now_ts is not None else int(time.time())
    return account.expire_at_ts > 0 and account.expire_at_ts <= current_ts


async def mark_fanbook_account_revoked(account: CalabiyauFanbookUser) -> None:
    """将当前账号本地凭据标记为已失效，保留 sign 以便手动 kq刷新令牌 再试一次。"""
    await CalabiyauFanbookUser.update_sign(
        bot_id=account.bot_id,
        user_id=account.user_id,
        sign=account.sign,
        expire_at_ts=REVOKED_EXPIRE_TS,
    )


async def _refresh_account_singleflight(account: CalabiyauFanbookUser) -> FanbookRefreshResult:
    key = (account.bot_id, account.user_id)
    inflight = _refresh_inflight.get(key)
    if inflight is not None:
        return await inflight

    # 同一账号并发只跑一次 ctk 刷新，避免旧 sign 在并发请求中被提前顶失效
    fut: asyncio.Future[FanbookRefreshResult] = asyncio.get_running_loop().create_future()
    _refresh_inflight[key] = fut
    try:
        device_id = account.device_id if account.device_id else str(uuid.uuid4())
        refreshed = await refresh_token(sign=account.sign, device_id=device_id)
        await CalabiyauFanbookUser.update_sign(
            bot_id=account.bot_id,
            user_id=account.user_id,
            sign=refreshed.sign,
            expire_at_ts=refreshed.expire_at_ts,
        )
        fut.set_result(refreshed)
        return refreshed
    except BaseException as exc:
        if not fut.done():
            fut.add_done_callback(_consume_future_exception)
            fut.set_exception(exc)
        raise
    finally:
        _refresh_inflight.pop(key, None)


async def prepare_fanbook_account(account: CalabiyauFanbookUser | None) -> FanbookAccountCheckResult:
    """在签到或查询前校验账号状态，并在临近过期时按需无感续期。"""
    if account is None or not account.sign:
        return FanbookAccountCheckResult(status="not_logged_in")

    now_ts = int(time.time())
    if is_fanbook_account_expired(account, now_ts):
        return FanbookAccountCheckResult(status="expired", account=account)

    if account.expire_at_ts > now_ts + REFRESH_THRESHOLD_S:
        return FanbookAccountCheckResult(status="ok", account=account)

    try:
        refreshed = await _refresh_account_singleflight(account)
    except FanbookError as exc:
        if exc.is_auth_error:
            await mark_fanbook_account_revoked(account)
            logger.warning(f"{_LOG_TAG} 账号 user_id={account.user_id} 按需续期失败，凭证已失效（code={exc.code}）")
            return FanbookAccountCheckResult(status="expired", account=account)
        logger.warning(f"{_LOG_TAG} 账号 user_id={account.user_id} 按需续期暂未成功，沿用当前凭证：{exc}")
        return FanbookAccountCheckResult(status="ok", account=account)

    updated_account = account.model_copy(
        update={
            "sign": refreshed.sign,
            "expire_at_ts": refreshed.expire_at_ts,
        }
    )
    logger.info(f"{_LOG_TAG} 账号 user_id={account.user_id} 签到前续期成功，新过期时间戳={refreshed.expire_at_ts}")
    return FanbookAccountCheckResult(status="ok", account=updated_account)


async def ensure_valid_fanbook_account(bot_id: str, user_id: str) -> FanbookAccountCheckResult:
    """读取当前会话的 Fanbook 账号并执行临近过期按需续期检查。"""
    account = await CalabiyauFanbookUser.get_account(bot_id, user_id)
    return await prepare_fanbook_account(account)


async def manual_refresh_fanbook_token(bot_id: str, user_id: str) -> FanbookManualRefreshResult:
    """响应 kq刷新令牌 命令，使用本地保存的 sign 手动尝试续期一次。"""
    account = await CalabiyauFanbookUser.get_account(bot_id, user_id)
    if account is None or not account.sign:
        return FanbookManualRefreshResult(
            success=False,
            message="当前尚未登录 Fanbook，请先发送 kq登录 或 kq扫码登录 完成登录。",
        )

    display_name = format_fanbook_account_name(account)
    try:
        refreshed = await _refresh_account_singleflight(account)
    except FanbookError as exc:
        if exc.is_transient:
            logger.warning(f"{_LOG_TAG} 手动续期遇临时异常 user_id={user_id}：{exc}")
            return FanbookManualRefreshResult(
                success=False,
                message=f"Fanbook 令牌续期失败（{exc}），请稍后重试；若持续失败请发送 kq登录 重新登录。",
            )
        await mark_fanbook_account_revoked(account)
        logger.warning(f"{_LOG_TAG} 手动续期失败 user_id={user_id} code={exc.code}：{exc}")
        return FanbookManualRefreshResult(
            success=False,
            message="Fanbook 令牌续期失败，登录凭证已失效，请发送 kq登录 或 kq扫码登录 重新登录。",
        )

    expire_text = datetime.fromtimestamp(refreshed.expire_at_ts, tz=_BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"{_LOG_TAG} 手动续期成功 user_id={user_id} expire_at={refreshed.expire_at_ts}")
    return FanbookManualRefreshResult(
        success=True,
        message=f"Fanbook 令牌续期成功：{display_name}\n新有效期至：{expire_text}",
    )
