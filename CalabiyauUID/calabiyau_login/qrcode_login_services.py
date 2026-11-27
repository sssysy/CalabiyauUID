"""Fanbook 客户端扫码登录流程编排与轮询。"""

from __future__ import annotations

import time
import uuid
import asyncio
import secrets
from typing import Literal

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event, Message
from gsuid_core.segment import MessageSegment
from gsuid_core.utils.cookie_manager.qrlogin import get_qrcode_base64

from .login_common import (
    LOG_TAG,
    DEFAULT_LOGIN_TTL_S,
    send_login_text,
    evict_login_sessions,
    save_and_notify_login,
    register_login_evictor,
)
from ..utils.api.fanbook import (
    FanbookError,
    FanbookUserSession,
    login_by_qr_token,
    poll_qrcode_login,
    create_qrcode_login,
)
from ..utils.utils.paths import IMG_CACHE_DIR

_QR_POLL_INTERVAL_S = 2.0
_QR_POLL_MAX_FAILURES = 3

_QR_SESSIONS: dict[tuple[str, str], str] = {}


def _evict_qr_session(bot_id: str, user_id: str) -> None:
    _QR_SESSIONS.pop((bot_id, user_id), None)


register_login_evictor(_evict_qr_session)


async def _build_qrcode_image(url: str, user_id: str, session_id: str, bot_id: str) -> bytes | str:
    IMG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    qr_path = IMG_CACHE_DIR / f"fanbook_qr_{user_id}_{session_id}.png"
    try:
        return await get_qrcode_base64(url, qr_path, bot_id)
    finally:
        if qr_path.exists():
            qr_path.unlink()


async def _send_qrcode_prompt(bot: Bot, ev: Event, qr_image: bytes | str, ttl_seconds: int) -> None:
    ttl_minutes = max(1, ttl_seconds // 60)
    prompt_text = "\n".join(
        [
            "[卡拉彼丘 Fanbook 扫码登录]",
            "请使用 Fanbook 客户端扫描下方二维码完成登录。",
            f"二维码 {ttl_minutes} 分钟内有效，请勿扫描他人二维码！",
        ]
    )
    segments: list[Message] = []
    if ev.group_id:
        segments.append(MessageSegment.at(ev.user_id))
        segments.append(MessageSegment.text(f" {prompt_text}\n"))
    else:
        segments.append(MessageSegment.text(f"{prompt_text}\n"))
    segments.append(MessageSegment.image(qr_image))
    await bot.send(segments)


async def _wait_for_qrcode_login(
    *,
    bot_id: str,
    user_id: str,
    session_id: str,
    code: str,
    device_id: str,
    ttl_seconds: int,
) -> tuple[Literal["success", "evicted", "expired"], FanbookUserSession | None]:
    session_key = (bot_id, user_id)
    deadline = time.monotonic() + ttl_seconds
    consecutive_failures = 0
    notified_scanned = False

    while time.monotonic() < deadline:
        if _QR_SESSIONS.get(session_key) != session_id:
            return "evicted", None

        try:
            poll_result = await poll_qrcode_login(code=code, device_id=device_id)
            consecutive_failures = 0
        except FanbookError:
            consecutive_failures += 1
            if consecutive_failures >= _QR_POLL_MAX_FAILURES:
                raise
            await asyncio.sleep(_QR_POLL_INTERVAL_S)
            continue

        if _QR_SESSIONS.get(session_key) != session_id:
            return "evicted", None
        if poll_result.status == "expired":
            return "expired", None
        if poll_result.status == "scanned" and not notified_scanned:
            notified_scanned = True
            logger.info(f"{LOG_TAG} 二维码已扫描，等待手机确认 user_id={user_id}")
        if poll_result.status == "confirmed":
            user_session = await login_by_qr_token(token=poll_result.token, device_id=device_id)
            return "success", user_session

        await asyncio.sleep(_QR_POLL_INTERVAL_S)

    return ("evicted" if _QR_SESSIONS.get(session_key) != session_id else "expired"), None


async def request_fanbook_qrcode_login(bot: Bot, ev: Event) -> None:
    """发起 Fanbook 扫码登录流程并等待客户端确认。"""
    evict_login_sessions(ev.bot_id, ev.user_id)
    session_key = (ev.bot_id, ev.user_id)
    session_id = secrets.token_hex(8)
    _QR_SESSIONS[session_key] = session_id
    device_id = str(uuid.uuid4())

    try:
        qr_session = await create_qrcode_login(device_id)
        ttl_seconds = max(60, min(DEFAULT_LOGIN_TTL_S, qr_session.expired_at_ts - int(time.time())))
        qr_image = await _build_qrcode_image(qr_session.url, ev.user_id, session_id, ev.bot_id)
        if _QR_SESSIONS.get(session_key) != session_id:
            return

        logger.info(f"{LOG_TAG} 生成扫码登录二维码 user_id={ev.user_id} ttl={ttl_seconds}s")
        await _send_qrcode_prompt(bot, ev, qr_image, ttl_seconds)

        wait_status, user_session = await _wait_for_qrcode_login(
            bot_id=ev.bot_id,
            user_id=ev.user_id,
            session_id=session_id,
            code=qr_session.code,
            device_id=device_id,
            ttl_seconds=ttl_seconds,
        )
    except FanbookError as exc:
        if _QR_SESSIONS.get(session_key) != session_id:
            return
        logger.warning(f"{LOG_TAG} 扫码登录失败 user_id={ev.user_id}: {exc}")
        await send_login_text(bot, ev, f"Fanbook 扫码登录失败：{exc}")
        return
    finally:
        if _QR_SESSIONS.get(session_key) == session_id:
            _QR_SESSIONS.pop(session_key, None)

    if wait_status == "evicted":
        return
    if wait_status == "expired" or user_session is None:
        await send_login_text(bot, ev, "Fanbook 扫码登录已过期或取消，请重新发送 kq扫码登录。")
        return

    await save_and_notify_login(bot, ev, user_session)
