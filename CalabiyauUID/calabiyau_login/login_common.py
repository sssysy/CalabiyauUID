"""Fanbook 登录公共凭据落库、登出、会话互斥与令牌续期。"""

from __future__ import annotations

from collections.abc import Callable

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from ..utils.api.fanbook import FanbookUserSession
from ..utils.helper.fanbook_auth import manual_refresh_fanbook_token
from ..utils.database.model_fanbook import CalabiyauFanbookUser

LOG_TAG = "[卡拉彼丘·Fanbook登录]"
DEFAULT_LOGIN_TTL_S = 300

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


async def refresh_fanbook_token(bot: Bot, ev: Event) -> None:
    """响应用户手动刷新令牌请求并回复结果。"""
    result = await manual_refresh_fanbook_token(ev.bot_id, ev.user_id)
    await send_login_text(bot, ev, result.message)
