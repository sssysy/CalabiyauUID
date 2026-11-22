"""Fanbook 网页短信登录会话管理与凭据落库。"""

from __future__ import annotations

import time
import uuid
import asyncio
import secrets
from typing import Literal
from pathlib import Path
from datetime import datetime, timedelta
from collections import OrderedDict
from dataclasses import dataclass

import httpx

from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.config import core_config
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.utils.cookie_manager.qrlogin import get_qrcode_base64

from ..calabiyau_config import CalabiyauConfig
from ..utils.api.fanbook import (
    FanbookError,
    FanbookUserSession,
    refresh_token,
    send_sms_code,
    login_by_mobile,
    fetch_captcha_app_id,
)
from ..utils.utils.paths import CACHE_DIR
from ..utils.database.model_fanbook import CalabiyauFanbookUser

_LOG_TAG = "[卡拉彼丘·Fanbook登录]"
_DEFAULT_LOGIN_TTL_S = 600
_MIN_LOGIN_TTL_S = 60
_MAX_LOGIN_TTL_S = 3600
_POLL_INTERVAL_S = 1.5
_MAX_CACHE_SIZE = 64
_REFRESH_THRESHOLD_S = 15 * 24 * 3600
_REVOKED_EXPIRE_TS = 1
_STARTUP_REFRESH_JOB_ID = "klbq_fanbook_token_refresh_startup"
_STARTUP_REFRESH_DELAY = timedelta(seconds=30)
_AUTH_EXPIRED_CODES = frozenset({1042, 1043})

_cached_public_ip: str = ""
_cached_public_ip_expire_at: float = 0.0
_PUBLIC_IP_TTL_S = 86400.0
_refresh_lock = asyncio.Lock()


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
    """基于单调时钟的 Fanbook 登录会话缓存。"""

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


def _get_bool_config(key: str) -> bool:
    value: object = CalabiyauConfig.get_config(key).data
    return value is True


def _get_str_config(key: str) -> str:
    value: object = CalabiyauConfig.get_config(key).data
    return value.strip() if isinstance(value, str) else ""


def get_login_ttl_seconds() -> int:
    value: object = CalabiyauConfig.get_config("FanbookLoginTTL").data
    if isinstance(value, int) and not isinstance(value, bool):
        return max(_MIN_LOGIN_TTL_S, min(_MAX_LOGIN_TTL_S, value))
    return _DEFAULT_LOGIN_TTL_S


async def _get_public_ip(fallback_host: str) -> str:
    global _cached_public_ip, _cached_public_ip_expire_at
    now = time.monotonic()
    if _cached_public_ip and now < _cached_public_ip_expire_at:
        return _cached_public_ip

    async with httpx.AsyncClient(timeout=httpx.Timeout(4.0)) as client:
        try:
            resp = await client.get("https://api.ipify.org/?format=json")
            payload: object = resp.json()
            if isinstance(payload, dict) and "ip" in payload and isinstance(payload["ip"], str):
                ip_addr = payload["ip"].strip()
                if ip_addr:
                    _cached_public_ip = ip_addr
                    _cached_public_ip_expire_at = now + _PUBLIC_IP_TTL_S
                    return ip_addr
        except (httpx.HTTPError, ValueError):
            pass

        try:
            resp = await client.get("https://httpbin.org/ip")
            payload_alt: object = resp.json()
            if isinstance(payload_alt, dict) and "origin" in payload_alt and isinstance(payload_alt["origin"], str):
                ip_addr = payload_alt["origin"].split(",")[0].strip()
                if ip_addr:
                    _cached_public_ip = ip_addr
                    _cached_public_ip_expire_at = now + _PUBLIC_IP_TTL_S
                    return ip_addr
        except (httpx.HTTPError, ValueError):
            pass

    return fallback_host


async def get_login_base_url() -> str:
    configured = _get_str_config("FanbookLoginUrl")
    if configured:
        normalized = configured if configured.startswith(("http://", "https://")) else f"https://{configured}"
        return normalized.rstrip("/")

    raw_host: object = core_config.get_config("HOST")
    raw_port: object = core_config.get_config("PORT")
    host = raw_host.strip() if isinstance(raw_host, str) and raw_host.strip() else "127.0.0.1"
    port = str(raw_port).strip() if raw_port is not None else "8765"
    if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
        host = await _get_public_ip(host)
    return f"http://{host}:{port}"


async def _send_text(bot: Bot, ev: Event, message: str) -> None:
    if ev.group_id:
        await bot.send([MessageSegment.at(ev.user_id), MessageSegment.text(f" {message}")])
        return
    await bot.send(message)


async def _send_login_prompt(bot: Bot, ev: Event, url: str, ttl_seconds: int) -> None:
    at_sender = bool(ev.group_id)
    use_forward = _get_bool_config("FanbookLoginForward")
    ttl_minutes = max(1, ttl_seconds // 60)

    if _get_bool_config("FanbookQRLogin"):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        qr_path: Path = CACHE_DIR / f"fb_login_{secrets.token_hex(6)}.png"
        try:
            qr_bytes = await get_qrcode_base64(url, qr_path, ev.bot_id)
            segments = [
                MessageSegment.text(f"[卡拉彼丘] 请在 {ttl_minutes} 分钟内扫描二维码打开 Fanbook 登录页：\n"),
                MessageSegment.image(qr_bytes),
            ]
            if use_forward:
                if not ev.group_id and ev.bot_id == "onebot":
                    await bot.send(segments)
                else:
                    await bot.send(MessageSegment.node(segments))
            else:
                await bot.send(segments, at_sender=at_sender)
        finally:
            qr_path.unlink(missing_ok=True)
        return

    target_url = f"https://docs.qq.com/scenario/link.html?url={url}" if _get_bool_config("FanbookTencentWord") else url
    lines = [
        f"[卡拉彼丘] 您的会话 ID 为【{ev.user_id}】",
        "请在浏览器打开下方链接完成 Fanbook 短信与滑块登录：",
        f" {target_url}" if use_forward else target_url,
        f"链接 {ttl_minutes} 分钟内有效。",
    ]
    content = "\n".join(lines)
    if use_forward:
        if not ev.group_id and ev.bot_id == "onebot":
            await bot.send(content)
        else:
            await bot.send(MessageSegment.node(lines))
        return
    await bot.send(content, at_sender=at_sender)


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
    LOGIN_CACHE.evict_user(ev.bot_id, ev.user_id)
    ttl_seconds = get_login_ttl_seconds()
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

    base_url = await get_login_base_url()
    login_url = f"{base_url}/kq/fanbook/i/{auth_token}"
    logger.info(f"{_LOG_TAG} 生成登录链接 user_id={ev.user_id} ttl={ttl_seconds}s")
    await _send_login_prompt(bot, ev, login_url, ttl_seconds)

    wait_status, session = await _wait_for_login(auth_token, state, ttl_seconds)
    if wait_status == "evicted":
        return
    if wait_status == "timeout" or session is None:
        await _send_text(bot, ev, "Fanbook 登录已超时，请重新发送 kq登录。")
        return

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
    display_id = session.fb_short_id if session.fb_short_id else session.fb_user_id
    identity = f"{session.nickname}（ID: {display_id}）" if session.nickname else f"ID: {display_id}"
    logger.info(f"{_LOG_TAG} 登录落库成功 user_id={ev.user_id} fb_user_id={session.fb_user_id}")
    await _send_text(bot, ev, f"Fanbook 登录成功：{identity}\n可发送 kq查看 确认账号状态。")


async def logout_fanbook(bot: Bot, ev: Event) -> None:
    """清除当前会话保存的 Fanbook 登录凭据。"""
    deleted = await CalabiyauFanbookUser.delete_account(ev.bot_id, ev.user_id)
    if not deleted:
        await _send_text(bot, ev, "当前尚未登录 Fanbook。")
        return
    logger.info(f"{_LOG_TAG} 已退出登录 user_id={ev.user_id}")
    await _send_text(bot, ev, "已退出 Fanbook 登录并清除本地凭证。")


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
                        f"{_LOG_TAG} 账号 user_id={account.user_id} 令牌已失效（code={exc.code}），标记为过期"
                    )
                else:
                    logger.warning(f"{_LOG_TAG} 账号 user_id={account.user_id} 自动续期失败：{exc}")
                continue

            await CalabiyauFanbookUser.update_sign(
                bot_id=account.bot_id,
                user_id=account.user_id,
                sign=refreshed.sign,
                expire_at_ts=refreshed.expire_at_ts,
            )
            refreshed_count += 1
            logger.info(
                f"{_LOG_TAG} 账号 user_id={account.user_id} 自动续期成功，新过期时间戳={refreshed.expire_at_ts}"
            )

        if refreshed_count > 0:
            logger.info(f"{_LOG_TAG} 本轮自动续期完成，共刷新 {refreshed_count} 个账号")


def schedule_startup_fanbook_refresh() -> None:
    """Core 启动后延迟 30 秒执行一次 Fanbook 令牌续期检查。"""
    scheduler.add_job(
        refresh_expiring_fanbook_tokens,
        "date",
        run_date=datetime.now().astimezone() + _STARTUP_REFRESH_DELAY,
        id=_STARTUP_REFRESH_JOB_ID,
        replace_existing=True,
    )
