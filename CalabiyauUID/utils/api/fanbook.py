"""Fanbook Web 认证与登录 HTTP 客户端。"""

from __future__ import annotations

import time
import uuid
import base64
import hashlib
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from gsuid_core.logger import logger

FANBOOK_WEB_BASE = "https://web.fanbook.cn/api/a1"
_APP_KEY = "ww0qqc0UHMsFtDUhGbh0"
_APP_SECRET = "dJcPo1dQHeMgDn1s8MQr"
_PLATFORM = "web"
_WEB_VERSION = "2.0.7"
_BUILD_NUMBER = "1128"
_DEFAULT_CAPTCHA_APP_ID = "197534779"
_DEFAULT_EXPIRE_SECONDS = 2592000
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

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]


class FanbookError(RuntimeError):
    """Fanbook Web 接口请求或业务校验失败。"""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


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


def fbe_encode(raw_text: str) -> str:
    """按 Fanbook Web 的 FBE 字母表对字符串做 Base64 字符替换编码。"""
    encoded_bytes = base64.b64encode(raw_text.encode("utf-8")).decode("ascii")
    return "".join(_FBE_TABLE[char] if char in _FBE_TABLE else char for char in encoded_bytes)


def _encode_signature_component(raw_text: str) -> str:
    # 与 JS encodeURIComponent + replace(/[!'()*]/g) 保持一致
    return quote(raw_text, safe="-_.~")


def _build_super_properties(device_id: str) -> str:
    payload = (
        f'{{"platform":"{_PLATFORM}","version":"{_WEB_VERSION}",'
        f'"device_id":"{device_id}","build_number":"{_BUILD_NUMBER}"}}'
    )
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def _serialize_json_compact(payload: dict[str, JsonValue]) -> str:
    parts: list[str] = []
    for key, value in payload.items():
        parts.append(f'"{_escape_json_str(key)}":{_serialize_json_value(value)}')
    return "{" + ",".join(parts) + "}"


def _escape_json_str(text: str) -> str:
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\b", "\\b")
        .replace("\f", "\\f")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return escaped


def _serialize_json_value(value: JsonValue) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{_escape_json_str(value)}"'
    if isinstance(value, list):
        return "[" + ",".join(_serialize_json_value(item) for item in value) + "]"
    return _serialize_json_compact(value)


def _build_signed_request(
    body: dict[str, JsonValue],
    *,
    device_id: str,
    authorization: str = "",
) -> tuple[dict[str, str], str]:
    nonce = str(uuid.uuid4())
    timestamp_ms = int(time.time() * 1000)
    signed_body = dict(body)
    signed_body["transaction"] = str(uuid.uuid4())
    request_body = _serialize_json_compact(signed_body)

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
    body: dict[str, JsonValue],
    *,
    device_id: str,
    authorization: str = "",
) -> tuple[dict[str, object], httpx.Headers]:
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
        raise FanbookError("Fanbook 服务连接失败，请稍后重试。") from exc

    if response.status_code >= 500:
        logger.warning(f"{_LOG_TAG} 请求 {path} 返回 HTTP {response.status_code}")
        raise FanbookError("Fanbook 服务暂时不可用，请稍后重试。")
    if response.status_code >= 400:
        logger.warning(f"{_LOG_TAG} 请求 {path} 返回 HTTP {response.status_code}")
        raise FanbookError(f"Fanbook 请求被拒绝（HTTP {response.status_code}）。")

    try:
        parsed: object = response.json()
    except ValueError as exc:
        logger.warning(f"{_LOG_TAG} 解析 {path} 响应 JSON 失败：{exc}")
        raise FanbookError("Fanbook 返回了无效响应，请稍后重试。") from exc

    if not isinstance(parsed, dict):
        raise FanbookError("Fanbook 响应格式异常。")

    code_obj = parsed["code"] if "code" in parsed else None
    code = code_obj if isinstance(code_obj, int) else None
    status_obj = parsed["status"] if "status" in parsed else None
    desc_obj = parsed["desc"] if "desc" in parsed else None
    message_obj = parsed["message"] if "message" in parsed else None
    desc = (
        desc_obj
        if isinstance(desc_obj, str) and desc_obj
        else (message_obj if isinstance(message_obj, str) and message_obj else "请求失败")
    )

    if code not in (1000, 200) and status_obj is not True:
        logger.warning(f"{_LOG_TAG} 接口 {path} 业务失败 code={code} desc={desc}")
        raise FanbookError(desc, code=code)

    return parsed, response.headers


def _extract_data_dict(parsed: dict[str, object]) -> dict[str, object]:
    data_obj = parsed["data"] if "data" in parsed else None
    if not isinstance(data_obj, dict):
        raise FanbookError("Fanbook 响应缺少有效 data 字段。")
    return data_obj


def _read_str_field(payload: dict[str, object], key: str, *, default: str = "") -> str:
    if key not in payload:
        return default
    value = payload[key]
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    return default


def _read_int_field(payload: dict[str, object], key: str, *, default: int = 0) -> int:
    if key not in payload:
        return default
    value = payload[key]
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default


async def fetch_captcha_app_id(device_id: str) -> str:
    """获取 Fanbook Web 当前使用的腾讯防水墙 CaptchaAppId。"""
    try:
        parsed, _ = await _post_fanbook_api("/api/common/alipay", {}, device_id=device_id)
    except FanbookError as exc:
        logger.warning(f"{_LOG_TAG} 获取 CaptchaAppId 失败，回退默认配置：{exc}")
        return _DEFAULT_CAPTCHA_APP_ID

    data_obj = parsed["data"] if "data" in parsed else None
    if not isinstance(data_obj, dict):
        return _DEFAULT_CAPTCHA_APP_ID
    captcha_obj = data_obj["t_captcha"] if "t_captcha" in data_obj else None
    if not isinstance(captcha_obj, dict):
        return _DEFAULT_CAPTCHA_APP_ID
    app_id = _read_str_field(captcha_obj, "app_id")
    return app_id if app_id else _DEFAULT_CAPTCHA_APP_ID


async def send_sms_code(
    *,
    mobile: str,
    area_code: str,
    captcha_ticket: str,
    captcha_rand_str: str,
    device_id: str,
) -> None:
    """提交腾讯验证码票据，向目标手机号发送 Fanbook 登录短信验证码。"""
    body: dict[str, JsonValue] = {
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
    body: dict[str, JsonValue] = {
        "device": _PLATFORM,
        "type": "mobile",
        "code": fbe_encode(sms_code),
        "area_code": area_code,
        "encrypt_type": "FBE",
        "mobile": fbe_encode(mobile),
    }
    parsed, headers = await _post_fanbook_api("/api/user/login", body, device_id=device_id)
    data = _extract_data_dict(parsed)

    fb_user_id = _read_str_field(data, "user_id")
    fb_short_id = _read_str_field(data, "username")
    nickname = _read_str_field(data, "nickname")
    avatar = _read_str_field(data, "avatar")
    sign = _read_str_field(data, "sign")
    if not sign and "authorization" in headers:
        sign = headers["authorization"]

    if not fb_user_id or not sign:
        raise FanbookError("登录成功但未返回完整的 Fanbook 用户凭据。")

    expire_at_ts = _read_int_field(data, "expire_time")
    if expire_at_ts <= 0:
        expire_at_ts = int(time.time()) + _DEFAULT_EXPIRE_SECONDS

    return FanbookUserSession(
        fb_user_id=fb_user_id,
        fb_short_id=fb_short_id,
        nickname=nickname,
        avatar=avatar,
        sign=sign,
        expire_at_ts=expire_at_ts,
        device_id=device_id,
    )


async def refresh_token(
    *,
    sign: str,
    device_id: str,
) -> FanbookRefreshResult:
    """调用 /api/common/ctk 刷新 Fanbook 登录令牌。"""
    parsed, headers = await _post_fanbook_api(
        "/api/common/ctk",
        {},
        device_id=device_id,
        authorization=sign,
    )
    new_sign = headers["authorization"] if "authorization" in headers else ""
    if not new_sign:
        raise FanbookError("Fanbook 未返回新的续期令牌。")

    data_obj = parsed["data"] if "data" in parsed else None
    expire_at_ts = 0
    if isinstance(data_obj, dict):
        expire_at_ts = _read_int_field(data_obj, "expire_time")
    if expire_at_ts <= 0:
        expire_at_ts = int(time.time()) + _DEFAULT_EXPIRE_SECONDS
    return FanbookRefreshResult(sign=new_sign, expire_at_ts=expire_at_ts)
