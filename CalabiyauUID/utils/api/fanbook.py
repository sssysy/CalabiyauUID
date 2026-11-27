"""Fanbook Web 认证与登录 HTTP 客户端。"""

from __future__ import annotations

import json
import time
import uuid
import base64
import hashlib
from typing import Any, Literal, Annotated
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from pydantic import Field, AliasPath, BaseModel, ConfigDict, BeforeValidator, ValidationError

from gsuid_core.logger import logger

FANBOOK_WEB_BASE = "https://web.fanbook.cn/api/a1"
_APP_KEY = "ww0qqc0UHMsFtDUhGbh0"
_APP_SECRET = "dJcPo1dQHeMgDn1s8MQr"
_PLATFORM = "web"
_WEB_VERSION = "2.0.7"
_BUILD_NUMBER = "1128"
_DEFAULT_CAPTCHA_APP_ID = "197534779"
_DEFAULT_EXPIRE_SECONDS = 2592000
_DEFAULT_QR_TTL_SECONDS = 300
_QR_EXPIRED_CODES = frozenset({1158})
_LOG_TAG = "[卡拉彼丘·Fanbook登录]"

_FBE_TABLE: dict[str, str] = {
    "A": "w",
    "B": "x",
    "C": "y",
    "D": "z",
    "E": "U",
    "F": "1",
    "G": "2",
    "H": "X",
    "I": "Y",
    "J": "5",
    "K": "a",
    "L": "b",
    "M": "8",
    "N": "d",
    "O": "+",
    "P": "f",
    "g": "Q",
    "h": "R",
    "i": "S",
    "j": "T",
    "k": "0",
    "l": "V",
    "m": "W",
    "n": "3",
    "o": "4",
    "p": "Z",
    "q": "6",
    "r": "7",
    "s": "c",
    "t": "9",
    "u": "e",
    "v": "/",
    "w": "A",
    "x": "B",
    "y": "C",
    "z": "D",
    "U": "E",
    "1": "F",
    "2": "G",
    "X": "H",
    "Y": "I",
    "5": "J",
    "a": "K",
    "b": "L",
    "8": "M",
    "d": "N",
    "+": "O",
    "f": "P",
    "Q": "g",
    "R": "h",
    "S": "i",
    "T": "j",
    "0": "k",
    "V": "l",
    "W": "m",
    "3": "n",
    "4": "o",
    "Z": "p",
    "6": "q",
    "7": "r",
    "c": "s",
    "9": "t",
    "e": "u",
    "/": "v",
}


class FanbookError(RuntimeError):
    """Fanbook Web 接口请求或业务校验失败。"""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        is_auth_error: bool = False,
        is_transient: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.is_auth_error = is_auth_error
        self.is_transient = is_transient


@dataclass(frozen=True, slots=True)
class FanbookUserSession:
    """Fanbook 登录成功后的账号会话凭据。"""

    fb_user_id: str
    fb_short_id: str
    nickname: str
    avatar: str
    sign: str
    expire_at_ts: int
    device_id: str


@dataclass(frozen=True, slots=True)
class FanbookRefreshResult:
    """Fanbook 令牌续期返回的新凭证。"""

    sign: str
    expire_at_ts: int


@dataclass(frozen=True, slots=True)
class FanbookQrCodeSession:
    """Fanbook 扫码登录二维码初始化结果。"""

    code: str
    url: str
    expired_at_ts: int
    device_id: str


@dataclass(frozen=True, slots=True)
class FanbookQrPollResult:
    """Fanbook 扫码登录单次轮询结果。"""

    status: Literal["waiting", "scanned", "confirmed", "expired"]
    token: str = ""


def _coerce_str(value: Any) -> str:
    return (
        value
        if isinstance(value, str)
        else (str(value) if isinstance(value, int) and not isinstance(value, bool) else "")
    )


def _coerce_int(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return int(value) if isinstance(value, str) and value.isdigit() else 0


def _coerce_signed_int(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lstrip("-").isdigit() and stripped != "-":
            return int(stripped)
    return 0


_CoercedStr = Annotated[str, BeforeValidator(_coerce_str)]
_OnlyStr = Annotated[str, BeforeValidator(lambda val: val if isinstance(val, str) else "")]
_CoercedInt = Annotated[int, BeforeValidator(_coerce_int)]
_SignedInt = Annotated[int, BeforeValidator(_coerce_signed_int)]
_OptInt = Annotated[
    int | None, BeforeValidator(lambda val: val if isinstance(val, int) and not isinstance(val, bool) else None)
]


class _FanbookModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class _FanbookEnvelope(_FanbookModel):
    code: _OptInt = None
    status: Any = None
    desc: _OnlyStr = ""
    message: _OnlyStr = ""
    data: Any = None

    @property
    def error_message(self) -> str:
        return self.desc or self.message or "请求失败"


class _AlipayData(_FanbookModel):
    app_id: _CoercedStr = Field(default="", validation_alias=AliasPath("t_captcha", "app_id"))


class _LoginData(_FanbookModel):
    user_id: _CoercedStr = ""
    username: _CoercedStr = ""
    nickname: _CoercedStr = ""
    avatar: _CoercedStr = ""
    sign: _CoercedStr = ""
    expire_time: _CoercedInt = 0


class _QrCodeData(_FanbookModel):
    code: _CoercedStr = ""
    url: _OnlyStr = ""
    status: _SignedInt = 0
    expired_at: _CoercedInt = 0
    token: _OnlyStr = ""


def fbe_encode(raw_text: str) -> str:
    """按 Fanbook Web 的 FBE 字母表对字符串做 Base64 字符替换编码。"""
    encoded_bytes = base64.b64encode(raw_text.encode("utf-8")).decode("ascii")
    return "".join(_FBE_TABLE.get(char, char) for char in encoded_bytes)


def _encode_signature_component(raw_text: str) -> str:
    # 与 JS encodeURIComponent + replace(/[!'()*]/g) 保持一致
    return quote(raw_text, safe="-_.~")


def _build_super_properties(device_id: str) -> str:
    payload = (
        f'{{"platform":"{_PLATFORM}","version":"{_WEB_VERSION}",'
        f'"device_id":"{device_id}","build_number":"{_BUILD_NUMBER}"}}'
    )
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def _build_signed_request(
    body: dict[str, Any],
    *,
    device_id: str,
    authorization: str = "",
) -> tuple[dict[str, str], str]:
    nonce = str(uuid.uuid4())
    timestamp_ms = int(time.time() * 1000)
    signed_body = dict(body)
    signed_body["transaction"] = str(uuid.uuid4())
    request_body = json.dumps(signed_body, separators=(",", ":"), ensure_ascii=False)

    sign_fields: list[tuple[str, str]] = [
        ("AppKey", _APP_KEY),
        ("Authorization", authorization),
        ("Nonce", nonce),
        ("Platform", _PLATFORM),
        ("RequestBody", request_body),
        ("Timestamp", str(timestamp_ms)),
    ]
    raw_sign_str = "&".join(f"{field_name}={field_val}" for field_name, field_val in sign_fields)
    raw_sign_str = f"{raw_sign_str}&{_APP_SECRET}"
    signature = hashlib.md5(_encode_signature_component(raw_sign_str).encode("utf-8")).hexdigest().lower()

    headers = {
        "Content-Type": "application/json",
        "Nonce": nonce,
        "Timestamp": str(timestamp_ms),
        "Authorization": authorization,
        "AppKey": _APP_KEY,
        "Platform": _PLATFORM,
        "signature": signature,
        "language": "zh-CN",
        "x-super-properties": _build_super_properties(device_id),
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Origin": "https://web.fanbook.cn",
        "Referer": "https://web.fanbook.cn/",
    }
    return headers, request_body


async def _post_fanbook_api(
    path: str,
    body: dict[str, Any],
    *,
    device_id: str,
    authorization: str = "",
) -> tuple[_FanbookEnvelope, httpx.Headers]:
    headers, request_body = _build_signed_request(
        body,
        device_id=device_id,
        authorization=authorization,
    )
    url = f"{FANBOOK_WEB_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.post(url, content=request_body.encode("utf-8"), headers=headers)
    except httpx.HTTPError as exc:
        logger.warning(f"{_LOG_TAG} 请求 {path} 网络异常：{exc}")
        raise FanbookError("Fanbook 服务连接失败，请稍后重试。", is_transient=True) from exc

    if response.status_code >= 500:
        logger.warning(f"{_LOG_TAG} 请求 {path} 返回 HTTP {response.status_code}")
        raise FanbookError("Fanbook 服务暂时不可用，请稍后重试。", is_transient=True)
    if response.status_code >= 400:
        logger.warning(f"{_LOG_TAG} 请求 {path} 返回 HTTP {response.status_code}")
        raise FanbookError(
            f"Fanbook 请求被拒绝（HTTP {response.status_code}）。",
            is_auth_error=response.status_code in (401, 403),
        )

    try:
        raw_payload: Any = response.json()
    except ValueError as exc:
        logger.warning(f"{_LOG_TAG} 解析 {path} 响应 JSON 失败：{exc}")
        raise FanbookError("Fanbook 返回了无效响应，请稍后重试。") from exc

    try:
        envelope = _FanbookEnvelope.model_validate(raw_payload)
    except ValidationError as exc:
        raise FanbookError("Fanbook 响应格式异常。") from exc

    if envelope.code not in (1000, 200) and envelope.status is not True:
        logger.warning(f"{_LOG_TAG} 接口 {path} 业务失败 code={envelope.code} desc={envelope.error_message}")
        raise FanbookError(
            envelope.error_message,
            code=envelope.code,
            is_auth_error=envelope.code in (1042, 1043),
        )

    return envelope, response.headers


async def fetch_captcha_app_id(device_id: str) -> str:
    """获取 Fanbook Web 当前使用的腾讯防水墙 CaptchaAppId。"""
    try:
        envelope, _ = await _post_fanbook_api("/api/common/alipay", {}, device_id=device_id)
    except FanbookError as exc:
        logger.warning(f"{_LOG_TAG} 获取 CaptchaAppId 失败，回退默认配置：{exc}")
        return _DEFAULT_CAPTCHA_APP_ID

    try:
        data = _AlipayData.model_validate(envelope.data)
    except ValidationError:
        return _DEFAULT_CAPTCHA_APP_ID
    return data.app_id or _DEFAULT_CAPTCHA_APP_ID


async def send_sms_code(
    *,
    mobile: str,
    area_code: str,
    captcha_ticket: str,
    captcha_rand_str: str,
    device_id: str,
) -> None:
    """提交腾讯验证码票据，向目标手机号发送 Fanbook 登录短信验证码。"""
    body: dict[str, Any] = {
        "mobile": fbe_encode(mobile),
        "area_code": area_code,
        "encrypt_type": "FBE",
        "device": _PLATFORM,
        "code_type": None,
        "captcha_ticket": captcha_ticket,
        "captcha_rand_str": captcha_rand_str,
    }
    await _post_fanbook_api("/api/common/verification", body, device_id=device_id)


async def login_by_mobile(
    *,
    mobile: str,
    area_code: str,
    sms_code: str,
    device_id: str,
) -> FanbookUserSession:
    """使用手机号与短信验证码完成 Fanbook Web 登录。"""
    body: dict[str, Any] = {
        "device": _PLATFORM,
        "type": "mobile",
        "code": fbe_encode(sms_code),
        "area_code": area_code,
        "encrypt_type": "FBE",
        "mobile": fbe_encode(mobile),
    }
    envelope, headers = await _post_fanbook_api("/api/user/login", body, device_id=device_id)
    return _parse_login_session(envelope, headers, device_id)


def _parse_login_session(
    envelope: _FanbookEnvelope,
    headers: httpx.Headers,
    device_id: str,
) -> FanbookUserSession:
    try:
        data = _LoginData.model_validate(envelope.data)
    except ValidationError as exc:
        raise FanbookError("Fanbook 响应缺少有效 data 字段。") from exc

    sign = data.sign or headers.get("authorization", "")
    if not data.user_id or not sign:
        raise FanbookError("登录成功但未返回完整的 Fanbook 用户凭据。")

    expire_at_ts = data.expire_time if data.expire_time > 0 else int(time.time()) + _DEFAULT_EXPIRE_SECONDS
    return FanbookUserSession(
        fb_user_id=data.user_id,
        fb_short_id=data.username,
        nickname=data.nickname,
        avatar=data.avatar,
        sign=sign,
        expire_at_ts=expire_at_ts,
        device_id=device_id,
    )


async def create_qrcode_login(device_id: str) -> FanbookQrCodeSession:
    """向 Fanbook 申请扫码登录二维码。"""
    envelope, _ = await _post_fanbook_api("/api/login/qrcode", {}, device_id=device_id)
    try:
        data = _QrCodeData.model_validate(envelope.data)
    except ValidationError as exc:
        raise FanbookError("Fanbook 二维码响应格式异常。") from exc
    if not data.code or not data.url:
        raise FanbookError("Fanbook 未返回有效的登录二维码。")

    expired_at_ts = data.expired_at if data.expired_at > 0 else int(time.time()) + _DEFAULT_QR_TTL_SECONDS
    return FanbookQrCodeSession(
        code=data.code,
        url=data.url,
        expired_at_ts=expired_at_ts,
        device_id=device_id,
    )


async def poll_qrcode_login(*, code: str, device_id: str) -> FanbookQrPollResult:
    """查询 Fanbook 扫码登录二维码当前状态。"""
    try:
        envelope, _ = await _post_fanbook_api(
            "/api/login/qrcode",
            {"code": code},
            device_id=device_id,
        )
    except FanbookError as exc:
        if exc.code in _QR_EXPIRED_CODES:
            return FanbookQrPollResult(status="expired")
        raise

    try:
        data = _QrCodeData.model_validate(envelope.data)
    except ValidationError as exc:
        raise FanbookError("Fanbook 扫码状态响应格式异常。") from exc

    if data.status == -1:
        return FanbookQrPollResult(status="expired")
    if data.status == 1:
        return FanbookQrPollResult(status="scanned")
    if data.status == 2:
        if not data.token:
            raise FanbookError("Fanbook 扫码已确认，但未返回登录令牌。")
        return FanbookQrPollResult(status="confirmed", token=data.token)
    return FanbookQrPollResult(status="waiting")


async def login_by_qr_token(*, token: str, device_id: str) -> FanbookUserSession:
    """使用扫码确认后返回的临时令牌完成 Fanbook Web 登录。"""
    body: dict[str, Any] = {
        "device": _PLATFORM,
        "type": "token",
        "token": token,
    }
    envelope, headers = await _post_fanbook_api("/api/user/login", body, device_id=device_id)
    return _parse_login_session(envelope, headers, device_id)


async def refresh_token(
    *,
    sign: str,
    device_id: str,
) -> FanbookRefreshResult:
    """调用 /api/common/ctk 刷新 Fanbook 登录令牌。"""
    envelope, headers = await _post_fanbook_api(
        "/api/common/ctk",
        {},
        device_id=device_id,
        authorization=sign,
    )
    new_sign = headers.get("authorization", "")
    if not new_sign:
        raise FanbookError("Fanbook 未返回新的续期令牌。")

    expire_at_ts = _LoginData.model_validate(envelope.data).expire_time if isinstance(envelope.data, dict) else 0
    if expire_at_ts <= 0:
        expire_at_ts = int(time.time()) + _DEFAULT_EXPIRE_SECONDS
    return FanbookRefreshResult(sign=new_sign, expire_at_ts=expire_at_ts)
