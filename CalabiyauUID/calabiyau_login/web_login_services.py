"""Fanbook 网页滑块短信登录会话管理。"""

from __future__ import annotations

import time
import uuid
import asyncio
import secrets
from typing import Literal
from collections import OrderedDict
from dataclasses import dataclass

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .login_common import (
    LOG_TAG,
    DEFAULT_LOGIN_TTL_S,
    send_login_text,
    evict_login_sessions,
    save_and_notify_login,
    register_login_evictor,
)
from ..calabiyau_config import CalabiyauConfig
from ..utils.api.fanbook import (
    FanbookError,
    FanbookUserSession,
    send_sms_code,
    login_by_mobile,
    fetch_captcha_app_id,
)

_POLL_INTERVAL_S = 1.5
_MAX_CACHE_SIZE = 64


@dataclass(slots=True, kw_only=True)
class LoginSessionState:
    """单个 Fanbook 网页登录会话状态。"""

    bot_id: str
    user_id: str
    device_id: str
    captcha_app_id: str
    done: bool = False
    evicted: bool = False
    session: FanbookUserSession | None = None


class TimedLoginCache:
    """基于单调时钟的 Fanbook 网页登录会话缓存。"""

    def __init__(self, maxsize: int = _MAX_CACHE_SIZE) -> None:
        self._store: OrderedDict[str, tuple[LoginSessionState, float]] = OrderedDict()
        self._maxsize = maxsize

    def set(self, key: str, state: LoginSessionState, ttl_seconds: int) -> None:
        self._sweep()
        if key in self._store:
            self._store.move_to_end(key)
        else:
            while len(self._store) >= self._maxsize:
                self._store.popitem(last=False)
        self._store[key] = (state, time.monotonic() + ttl_seconds)

    def get(self, key: str) -> LoginSessionState | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        state, expire_at = entry
        if expire_at <= time.monotonic():
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return state

    def pop(self, key: str) -> LoginSessionState | None:
        entry = self._store.pop(key, None)
        if entry is None:
            return None
        state, expire_at = entry
        if expire_at <= time.monotonic():
            return None
        return state

    def evict_user(self, bot_id: str, user_id: str) -> None:
        self._sweep()
        stale_keys = [
            token for token, (state, _) in self._store.items() if state.bot_id == bot_id and state.user_id == user_id
        ]
        for token in stale_keys:
            removed = self._store.pop(token, None)
            if removed is not None:
                removed[0].evicted = True

    def _sweep(self) -> None:
        now = time.monotonic()
        expired = [token for token, (_, expire_at) in self._store.items() if expire_at <= now]
        for token in expired:
            self._store.pop(token, None)


LOGIN_CACHE = TimedLoginCache()
register_login_evictor(LOGIN_CACHE.evict_user)


def _get_str_config(key: str) -> str:
    value: object = CalabiyauConfig.get_config(key).data
    return value.strip() if isinstance(value, str) else ""


def get_login_base_url() -> str | None:
    configured = _get_str_config("FanbookLoginUrl")
    if not configured:
        return None
    normalized = configured if configured.startswith(("http://", "https://")) else f"https://{configured}"
    if not normalized.removeprefix("https://").removeprefix("http://").strip("/"):
        return None
    return normalized.rstrip("/")


async def _send_login_prompt(bot: Bot, ev: Event, url: str, ttl_seconds: int) -> None:
    at_sender = bool(ev.group_id)
    ttl_minutes = max(1, ttl_seconds // 60)
    lines = [
        "[卡拉彼丘 Fanbook 社区登录]",
        f"登录链接：{url}",
        f"校验码：{ev.user_id}",
        f"链接 {ttl_minutes} 分钟内有效。",
        "【登录前请核对校验码正确无误！】",
    ]
    await bot.send("\n".join(lines), at_sender=at_sender)


async def send_fanbook_sms(
    *,
    auth_token: str,
    area_code: str,
    mobile: str,
    ticket: str,
    rand_str: str,
) -> tuple[bool, str]:
    state = LOGIN_CACHE.get(auth_token)
    if state is None:
        return False, "登录链接已过期，请重新发送 kq登录。"
    if state.done:
        return False, "当前会话已完成登录，无需重复获取验证码。"
    cleaned_mobile = mobile.strip()
    cleaned_area = area_code.strip() or "86"
    if not cleaned_mobile.isdigit():
        return False, "手机号格式不正确。"
    if not ticket.strip() or not rand_str.strip():
        return False, "安全滑块验证票据无效，请重试。"
    try:
        await send_sms_code(
            mobile=cleaned_mobile,
            area_code=cleaned_area,
            captcha_ticket=ticket.strip(),
            captcha_rand_str=rand_str.strip(),
            device_id=state.device_id,
        )
    except FanbookError as exc:
        return False, f"短信发送失败：{exc}"
    return True, "短信验证码已发送，请注意查收。"


async def submit_fanbook_login(
    *,
    auth_token: str,
    area_code: str,
    mobile: str,
    sms_code: str,
) -> tuple[bool, str]:
    state = LOGIN_CACHE.get(auth_token)
    if state is None:
        return False, "登录链接已过期，请重新发送 kq登录。"
    if state.done:
        return True, "Fanbook 登录已完成。"
    cleaned_mobile = mobile.strip()
    cleaned_code = sms_code.strip()
    cleaned_area = area_code.strip() or "86"
    if not cleaned_mobile.isdigit():
        return False, "手机号格式不正确。"
    if not cleaned_code.isdigit() or len(cleaned_code) < 4:
        return False, "请输入有效的短信验证码。"

    try:
        session = await login_by_mobile(
            mobile=cleaned_mobile,
            area_code=cleaned_area,
            sms_code=cleaned_code,
            device_id=state.device_id,
        )
    except FanbookError as exc:
        return False, f"登录失败：{exc}"

    state.session = session
    state.done = True
    return True, "Fanbook 登录成功。"


async def _wait_for_login(
    auth_token: str,
    expected_state: LoginSessionState,
    ttl_seconds: int,
) -> tuple[Literal["success", "evicted", "timeout"], FanbookUserSession | None]:
    deadline = time.monotonic() + ttl_seconds
    while time.monotonic() < deadline:
        if expected_state.evicted:
            return "evicted", None
        current = LOGIN_CACHE.get(auth_token)
        if current is None or current is not expected_state:
            return "evicted" if expected_state.evicted else "timeout", None
        if current.done and current.session is not None:
            LOGIN_CACHE.pop(auth_token)
            return "success", current.session
        await asyncio.sleep(_POLL_INTERVAL_S)
    LOGIN_CACHE.pop(auth_token)
    return ("evicted" if expected_state.evicted else "timeout"), None


async def request_fanbook_login(bot: Bot, ev: Event) -> None:
    """发起 Fanbook 网页滑块短信登录流程并等待完成。"""
    base_url = get_login_base_url()
    if base_url is None:
        logger.info(f"{LOG_TAG} 未配置 FanbookLoginUrl，拒绝发起网页登录 user_id={ev.user_id}")
        await send_login_text(bot, ev, "未开启网页登录，请使用【kq扫码登录】命令登录！。")
        return

    evict_login_sessions(ev.bot_id, ev.user_id)
    ttl_seconds = DEFAULT_LOGIN_TTL_S
    auth_token = secrets.token_urlsafe(16)
    device_id = str(uuid.uuid4())
    captcha_app_id = await fetch_captcha_app_id(device_id)
    state = LoginSessionState(
        bot_id=ev.bot_id,
        user_id=ev.user_id,
        device_id=device_id,
        captcha_app_id=captcha_app_id,
    )
    LOGIN_CACHE.set(auth_token, state, ttl_seconds)

    login_url = f"{base_url}/kq/fanbook/i/{auth_token}"
    logger.info(f"{LOG_TAG} 生成登录链接 user_id={ev.user_id} ttl={ttl_seconds}s")
    await _send_login_prompt(bot, ev, login_url, ttl_seconds)

    wait_status, session = await _wait_for_login(auth_token, state, ttl_seconds)
    if wait_status == "evicted":
        return
    if wait_status == "timeout" or session is None:
        await send_login_text(bot, ev, "Fanbook 登录已超时，请重新发送 kq登录。")
        return

    await save_and_notify_login(bot, ev, session)
