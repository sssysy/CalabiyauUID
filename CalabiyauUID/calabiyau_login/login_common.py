"""Fanbook 登录公共凭据落库、登出、会话互斥与令牌续期。"""

from __future__ import annotations

import time
import uuid
import asyncio
from datetime import datetime, timedelta
from collections.abc import Callable

from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from ..utils.api.fanbook import FanbookError, FanbookUserSession, refresh_token
from ..utils.database.model_fanbook import CalabiyauFanbookUser

LOG_TAG = "[卡拉彼丘·Fanbook登录]"
DEFAULT_LOGIN_TTL_S = 300
_REFRESH_THRESHOLD_S = 15 * 24 * 3600
_REVOKED_EXPIRE_TS = 1
_STARTUP_REFRESH_JOB_ID = "klbq_fanbook_token_refresh_startup"
_STARTUP_REFRESH_DELAY = timedelta(seconds=30)
_AUTH_EXPIRED_CODES = frozenset({1042, 1043})

_refresh_lock = asyncio.Lock()
_evictors: list[Callable[[str, str], None]] = []


def register_login_evictor(evictor: Callable[[str, str], None]) -> None:
    """注册登录方式对应的旧会话清理函数，避免不同登录模块互相导入。"""
    if evictor not in _evictors:
        _evictors.append(evictor)


def evict_login_sessions(bot_id: str, user_id: str) -> None:
    """驱逐同一用户所有未完成的登录等待会话。"""
    for evictor in _evictors:
        evictor(bot_id, user_id)


async def send_login_text(bot: Bot, ev: Event, message: str) -> None:
    """向当前会话发送登录相关文本提示，群聊自动 @ 触发者。"""
    if ev.group_id:
        await bot.send([MessageSegment.at(ev.user_id), MessageSegment.text(f" {message}")])
        return
    await bot.send(message)


async def save_and_notify_login(bot: Bot, ev: Event, session: FanbookUserSession) -> None:
    """将登录凭据写入数据库并向用户发送登录成功通知。"""
    await CalabiyauFanbookUser.upsert_account(
        bot_id=ev.bot_id,
        user_id=ev.user_id,
        fb_user_id=session.fb_user_id,
        fb_short_id=session.fb_short_id,
        nickname=session.nickname,
        avatar=session.avatar,
        sign=session.sign,
        device_id=session.device_id,
        expire_at_ts=session.expire_at_ts,
    )
    display_name = (
        session.nickname if session.nickname else (session.fb_short_id if session.fb_short_id else session.fb_user_id)
    )
    logger.info(f"{LOG_TAG} 登录落库成功 user_id={ev.user_id} fb_user_id={session.fb_user_id}")
    await send_login_text(bot, ev, f"Fanbook 登录成功：{display_name}")


async def logout_fanbook(bot: Bot, ev: Event) -> None:
    """清除当前会话保存的 Fanbook 登录凭据。"""
    deleted = await CalabiyauFanbookUser.delete_account(ev.bot_id, ev.user_id)
    if not deleted:
        await send_login_text(bot, ev, "当前尚未登录 Fanbook。")
        return
    logger.info(f"{LOG_TAG} 已退出登录 user_id={ev.user_id}")
    await send_login_text(bot, ev, "已退出 Fanbook 登录并清除本地凭证。")


async def refresh_expiring_fanbook_tokens() -> None:
    """巡检所有已保存的 Fanbook 账号，在过期前 15 天内自动无感续期。"""
    async with _refresh_lock:
        accounts = await CalabiyauFanbookUser.list_accounts()
        if not accounts:
            return

        now_ts = int(time.time())
        refreshed_count = 0
        for account in accounts:
            if not account.sign or account.expire_at_ts == _REVOKED_EXPIRE_TS:
                continue
            if account.expire_at_ts > now_ts + _REFRESH_THRESHOLD_S:
                continue

            device_id = account.device_id if account.device_id else str(uuid.uuid4())
            try:
                refreshed = await refresh_token(sign=account.sign, device_id=device_id)
            except FanbookError as exc:
                if exc.code in _AUTH_EXPIRED_CODES:
                    await CalabiyauFanbookUser.update_sign(
                        bot_id=account.bot_id,
                        user_id=account.user_id,
                        sign=account.sign,
                        expire_at_ts=_REVOKED_EXPIRE_TS,
                    )
                    logger.warning(
                        f"{LOG_TAG} 账号 user_id={account.user_id} 令牌已失效（code={exc.code}），标记为过期"
                    )
                else:
                    logger.warning(f"{LOG_TAG} 账号 user_id={account.user_id} 自动续期失败：{exc}")
                continue

            await CalabiyauFanbookUser.update_sign(
                bot_id=account.bot_id,
                user_id=account.user_id,
                sign=refreshed.sign,
                expire_at_ts=refreshed.expire_at_ts,
            )
            refreshed_count += 1
            logger.info(f"{LOG_TAG} 账号 user_id={account.user_id} 自动续期成功，新过期时间戳={refreshed.expire_at_ts}")

        if refreshed_count > 0:
            logger.info(f"{LOG_TAG} 本轮自动续期完成，共刷新 {refreshed_count} 个账号")


def schedule_startup_fanbook_refresh() -> None:
    """Core 启动后延迟 30 秒执行一次 Fanbook 令牌续期检查。"""
    scheduler.add_job(
        refresh_expiring_fanbook_tokens,
        "date",
        run_date=datetime.now().astimezone() + _STARTUP_REFRESH_DELAY,
        id=_STARTUP_REFRESH_JOB_ID,
        replace_existing=True,
    )
