"""Fanbook 卡拉彼丘官方社群每日签到小程序 HTTP 客户端。"""

from __future__ import annotations

import json
import time
import asyncio
import hashlib
import secrets
from typing import Any, Annotated
from datetime import datetime, timezone, timedelta

import httpx
from pydantic import Field, AliasPath, BaseModel, ConfigDict, BeforeValidator, ValidationError

from gsuid_core.logger import logger

from ..utils.cache import AsyncTtlCache

_SIGN_API_BASE = "https://open.fanbook.cn/mp/138519745866498048/368331042878263296/sign/api"
_SIGN_REFERER = (
    "https://open.fanbook.cn/mp/138519745866498048/368331042878263296/sign/"
    "?enter_type=message_card&view=1&fb_redirect&open_type=mp"
)
_SHOP_API_BASE = "https://open.fanbook.cn/mp/138519745866498048/368331042878263296/credit-shop/api"
_SHOP_REFERER = "https://open.fanbook.cn/mp/138519745866498048/368331042878263296/credit-shop/"
_SIGN_APP_KEY = "z2cg4sg3vokll9pydc5d"
_SIGN_APP_SECRET = "f8f8zvnzi87tuy27cweb"
_NONCE_ALPHABET = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"
CALABIYAU_GUILD_ID = "167099262725787648"
CALABIYAU_SIGN_CHANNEL_ID = "408518973252960256"
_QUERY_MAX_ATTEMPTS = 12
_QUERY_RETRY_DELAY_S = 0.5
_CODE_NOT_SIGNED_YET = 70000
_SHOP_TOKEN_INVALID_CODES = (7, 401, 80007)
_BEIJING_TZ = timezone(timedelta(hours=8))
_LOG_TAG = "[卡拉彼丘·Fanbook签到]"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_SHOP_TOKEN_CACHE_MAXSIZE = 512
_SHOP_TOKEN_CACHE_TTL_SECONDS = 86400.0

_shop_client_id: str = ""
_shop_token_cache: AsyncTtlCache[str, tuple[str, str]] = AsyncTtlCache(
    maxsize=_SHOP_TOKEN_CACHE_MAXSIZE,
    ttl_seconds=_SHOP_TOKEN_CACHE_TTL_SECONDS,
)


class FanbookSignError(RuntimeError):
    """Fanbook 签到小程序接口调用或业务失败。"""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        is_auth_error: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.is_auth_error = is_auth_error


def _coerce_int(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return int(value) if isinstance(value, str) and value.isdigit() else 0


def _coerce_str(value: Any) -> str:
    return (
        value
        if isinstance(value, str)
        else (str(value) if isinstance(value, int) and not isinstance(value, bool) else "")
    )


def _parse_point(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ValueError("invalid point")


_CoercedInt = Annotated[int, BeforeValidator(_coerce_int)]
_OptInt = Annotated[
    int | None, BeforeValidator(lambda val: val if isinstance(val, int) and not isinstance(val, bool) else None)
]
_CoercedStr = Annotated[str, BeforeValidator(_coerce_str)]
_OnlyStr = Annotated[str, BeforeValidator(lambda val: val if isinstance(val, str) else "")]


class _MpModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class FanbookSignResult(BaseModel):
    """Fanbook 每日签到结果详情。"""

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")

    score: _CoercedInt = Field(default=0, validation_alias=AliasPath("signInfo", "score"))
    rank: _CoercedInt = Field(default=0, validation_alias=AliasPath("signInfo", "rank"))
    sum_sign_days: _CoercedInt = Field(default=0, validation_alias=AliasPath("signInfo", "sumSignDays"))
    continuous_sign_days: _CoercedInt = Field(default=0, validation_alias=AliasPath("signInfo", "continuousSignDays"))
    shop_point: _CoercedInt = Field(default=0, validation_alias=AliasPath("userInfo", "shopPoint"))
    sign_date_time: _CoercedStr = Field(default="", validation_alias=AliasPath("signInfo", "signDateTime"))
    reply_text: _OnlyStr = Field(default="", validation_alias=AliasPath("signInfo", "replays", 0))
    already_signed: bool = False


class _MpEnvelope(_MpModel):
    code: _OptInt = None
    msg: _OnlyStr = ""
    data: Any = None


class _ShopPayload(_MpModel):
    client_id: _CoercedStr = ""
    token: _CoercedStr = ""


class _ShopMeInfo(_MpModel):
    point: Annotated[int, BeforeValidator(_parse_point)]


def beijing_today_str() -> str:
    """返回北京时间 YYYY-MM-DD 日期字符串。"""
    return datetime.now(_BEIJING_TZ).strftime("%Y-%m-%d")


def _generate_nonce(length: int = 20) -> str:
    return "".join(secrets.choice(_NONCE_ALPHABET) for _ in range(length))


def _build_common_headers(
    *,
    nonce: str,
    timestamp_ms: str,
    signature: str,
    referer: str,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    headers = {
        "AppKey": _SIGN_APP_KEY,
        "Nonce": nonce,
        "Timestamp": timestamp_ms,
        "Signature": signature,
        "Content-Type": "application/json",
        "Origin": "https://open.fanbook.cn",
        "Referer": referer,
        "User-Agent": _USER_AGENT,
    }
    if extra_headers is not None:
        headers.update(extra_headers)
    return headers


def _build_get_headers(
    params: dict[str, str],
    *,
    referer: str = _SIGN_REFERER,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    nonce = _generate_nonce()
    timestamp_ms = str(int(time.time() * 1000))
    query_suffix = "".join(f"&{key}={val}" for key, val in params.items())
    raw = f"{_SIGN_APP_SECRET}&AppKey={_SIGN_APP_KEY}&Nonce={nonce}&Timestamp={timestamp_ms}{query_suffix}&{_SIGN_APP_SECRET}"
    signature = hashlib.md5(raw.encode("utf-8")).hexdigest().lower()
    return _build_common_headers(
        nonce=nonce,
        timestamp_ms=timestamp_ms,
        signature=signature,
        referer=referer,
        extra_headers=extra_headers,
    )


def _build_post_headers_and_body(
    payload: dict[str, str],
    *,
    referer: str = _SIGN_REFERER,
    extra_headers: dict[str, str] | None = None,
) -> tuple[dict[str, str], str]:
    nonce = _generate_nonce()
    timestamp_ms = str(int(time.time() * 1000))
    body_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    raw = (
        f"{_SIGN_APP_SECRET}&AppKey={_SIGN_APP_KEY}&Nonce={nonce}"
        f"&Timestamp={timestamp_ms}&requestBody={body_str}&{_SIGN_APP_SECRET}"
    )
    signature = hashlib.md5(raw.encode("utf-8")).hexdigest().lower()
    headers = _build_common_headers(
        nonce=nonce,
        timestamp_ms=timestamp_ms,
        signature=signature,
        referer=referer,
        extra_headers=extra_headers,
    )
    return headers, body_str


def _parse_envelope(response: httpx.Response, *, service_name: str, path: str) -> _MpEnvelope | None:
    try:
        raw_payload: Any = response.json()
    except ValueError:
        return None
    try:
        return _MpEnvelope.model_validate(raw_payload)
    except ValidationError:
        logger.warning(f"{_LOG_TAG} {service_name} {path} 响应非 JSON 对象")
        return None


async def _request_mp_api(
    method: str,
    path: str,
    *,
    base_url: str,
    referer: str,
    service_name: str,
    params: dict[str, str] | None = None,
    payload: dict[str, str] | None = None,
    sign_token: str = "",
    extra_headers: dict[str, str] | None = None,
) -> Any:
    url = f"{base_url}{path}"
    cookies = {"token": sign_token} if sign_token else None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0), cookies=cookies) as client:
            if method == "GET":
                query_params = params if params is not None else {}
                headers = _build_get_headers(query_params, referer=referer, extra_headers=extra_headers)
                response = await client.get(url, params=query_params, headers=headers)
            else:
                body_payload = payload if payload is not None else {}
                headers, body_str = _build_post_headers_and_body(
                    body_payload, referer=referer, extra_headers=extra_headers
                )
                response = await client.post(url, content=body_str.encode("utf-8"), headers=headers)
    except httpx.HTTPError as exc:
        logger.warning(f"{_LOG_TAG} 请求 {service_name} {path} 网络异常：{exc}")
        raise FanbookSignError(f"{service_name}连接失败，请稍后重试。") from exc

    envelope = _parse_envelope(response, service_name=service_name, path=path)
    if response.status_code == 401:
        err_code = envelope.code if envelope is not None and envelope.code is not None else 401
        err_msg = (
            envelope.msg if envelope is not None else ""
        ) or "Fanbook 登录凭证已过期，请发送 kq刷新令牌 尝试续期，失败请发送 kq登录 重新登录。"
        logger.warning(f"{_LOG_TAG} {service_name} {path} 鉴权失败（HTTP 401, code={err_code}）：{err_msg}")
        raise FanbookSignError(err_msg, code=err_code, is_auth_error=True)

    if response.status_code >= 400:
        logger.warning(f"{_LOG_TAG} 请求 {service_name} {path} 返回 HTTP {response.status_code}")
        raise FanbookSignError(f"{service_name}接口异常（HTTP {response.status_code}）。", code=response.status_code)

    if envelope is None:
        raise FanbookSignError(f"{service_name}接口返回了无效数据。")

    if envelope.code != 0:
        msg = envelope.msg or f"{service_name}请求失败"
        logger.warning(f"{_LOG_TAG} {service_name} {path} 业务返回 code={envelope.code} msg={msg}")
        raise FanbookSignError(msg, code=envelope.code)
    return envelope.data


async def _request_sign_api(
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    payload: dict[str, str] | None = None,
    sign_token: str = "",
) -> Any:
    return await _request_mp_api(
        method,
        path,
        base_url=_SIGN_API_BASE,
        referer=_SIGN_REFERER,
        service_name="Fanbook 签到服务",
        params=params,
        payload=payload,
        sign_token=sign_token,
    )


def _parse_sign_result(data_obj: Any, *, already_signed: bool = False) -> FanbookSignResult | None:
    if not isinstance(data_obj, dict) or not isinstance(data_obj.get("signInfo"), dict):
        return None
    return FanbookSignResult.model_validate(data_obj).model_copy(update={"already_signed": already_signed})


def _build_user_payload(fb_user_id: str, fb_short_id: str) -> dict[str, str]:
    return {
        "channelId": CALABIYAU_SIGN_CHANNEL_ID,
        "guildId": CALABIYAU_GUILD_ID,
        "longUid": fb_user_id,
        "shortUid": fb_short_id,
    }


async def get_gain_point_able() -> int:
    """查询当前社区每日签到可获得的基础积分数。"""
    data = await _request_sign_api("GET", "/open/getGainPointAble", params={"guild": CALABIYAU_GUILD_ID})
    return data if isinstance(data, int) and not isinstance(data, bool) else 0


async def query_sign_result(
    *,
    fb_user_id: str,
    fb_short_id: str,
    sign_token: str = "",
    already_signed: bool = False,
) -> FanbookSignResult | None:
    """查询指定用户的每日签到结果。"""
    try:
        data = await _request_sign_api(
            "POST",
            "/open/querySignResult",
            payload=_build_user_payload(fb_user_id, fb_short_id),
            sign_token=sign_token,
        )
    except FanbookSignError as exc:
        if exc.code == _CODE_NOT_SIGNED_YET:
            return None
        raise
    return _parse_sign_result(data, already_signed=already_signed)


def _is_already_signed_error(exc: FanbookSignError) -> bool:
    message = str(exc)
    return "已签" in message or "重复" in message


async def perform_daily_sign(
    *,
    fb_user_id: str,
    fb_short_id: str,
    sign_token: str = "",
) -> FanbookSignResult:
    """执行 Fanbook 社区每日签到并轮询查询签到结果。"""
    if not fb_user_id or not fb_short_id:
        raise FanbookSignError("Fanbook 账号缺少 user_id 或 short_id，请重新 kq登录。")

    existing = await query_sign_result(
        fb_user_id=fb_user_id,
        fb_short_id=fb_short_id,
        sign_token=sign_token,
        already_signed=True,
    )
    if existing is not None:
        return existing

    already_signed = False
    try:
        await _request_sign_api(
            "POST",
            "/open/sign",
            payload=_build_user_payload(fb_user_id, fb_short_id),
            sign_token=sign_token,
        )
    except FanbookSignError as exc:
        if not _is_already_signed_error(exc):
            raise
        already_signed = True

    for attempt in range(1, _QUERY_MAX_ATTEMPTS + 1):
        await asyncio.sleep(_QUERY_RETRY_DELAY_S)
        result = await query_sign_result(
            fb_user_id=fb_user_id,
            fb_short_id=fb_short_id,
            sign_token=sign_token,
            already_signed=already_signed,
        )
        if result is not None:
            return result
        logger.debug(f"{_LOG_TAG} 第 {attempt}/{_QUERY_MAX_ATTEMPTS} 次查询签到结果仍在队列中")

    raise FanbookSignError("签到结果同步超时，请稍后再试。")


async def _get_shop_client_id() -> str:
    global _shop_client_id
    if _shop_client_id:
        return _shop_client_id

    data = await _request_mp_api(
        "GET",
        "/core/v1/client",
        base_url=_SHOP_API_BASE,
        referer=_SHOP_REFERER,
        service_name="Fanbook 积分商城",
        params={"guild_id": CALABIYAU_GUILD_ID},
    )
    try:
        client_id = _ShopPayload.model_validate(data).client_id
    except ValidationError as exc:
        raise FanbookSignError("Fanbook 积分商城 client 配置响应异常。") from exc
    if not client_id:
        raise FanbookSignError("Fanbook 积分商城未返回有效的 client_id。")
    _shop_client_id = client_id
    return client_id


async def _exchange_shop_token(*, fb_user_id: str, sign_token: str) -> str:
    client_id = await _get_shop_client_id()
    try:
        data = await _request_mp_api(
            "POST",
            "/core/v2/user_token/login",
            base_url=_SHOP_API_BASE,
            referer=_SHOP_REFERER,
            service_name="Fanbook 积分商城",
            payload={"clientId": client_id, "userToken": sign_token},
        )
    except FanbookSignError as exc:
        if exc.is_auth_error or exc.code in _SHOP_TOKEN_INVALID_CODES:
            raise FanbookSignError(
                "Fanbook 登录凭证已过期，请发送 kq刷新令牌 尝试续期，失败请发送 kq登录 重新登录。",
                code=401,
                is_auth_error=True,
            ) from exc
        raise

    try:
        shop_token = _ShopPayload.model_validate(data).token
    except ValidationError as exc:
        raise FanbookSignError("Fanbook 积分商城登录响应格式异常。") from exc
    if not shop_token:
        raise FanbookSignError("Fanbook 积分商城未返回有效的访问令牌。")
    if fb_user_id:
        _shop_token_cache.set(fb_user_id, (sign_token, shop_token))
    return shop_token


def _get_cached_shop_token(*, fb_user_id: str, sign_token: str) -> str:
    if not fb_user_id:
        return ""
    hit = _shop_token_cache.get(fb_user_id)
    if hit is None:
        return ""
    cached_sign, cached_bearer = hit.value
    if cached_sign == sign_token:
        return cached_bearer
    _shop_token_cache.delete(fb_user_id)
    return ""


async def _fetch_me_info(*, shop_token: str) -> _ShopMeInfo:
    data = await _request_mp_api(
        "GET",
        "/common/v1/me/info",
        base_url=_SHOP_API_BASE,
        referer=_SHOP_REFERER,
        service_name="Fanbook 积分商城",
        extra_headers={"Authorization": f"Bearer {shop_token}"},
    )
    if not isinstance(data, dict):
        raise FanbookSignError("Fanbook 积分商城用户信息格式异常。")
    if "point" not in data:
        raise FanbookSignError("Fanbook 积分商城未返回积分字段。")
    try:
        return _ShopMeInfo.model_validate(data)
    except ValidationError as exc:
        raise FanbookSignError("Fanbook 积分商城返回的积分数值格式异常。") from exc


async def query_shop_points(*, fb_user_id: str, sign_token: str) -> int:
    """查询当前用户在卡拉彼丘 Fanbook 积分商城的总积分。"""
    if not sign_token:
        raise FanbookSignError("Fanbook 账号缺少登录凭证，请发送 kq登录 重新登录。")

    shop_token = _get_cached_shop_token(fb_user_id=fb_user_id, sign_token=sign_token)
    if not shop_token:
        shop_token = await _exchange_shop_token(fb_user_id=fb_user_id, sign_token=sign_token)

    try:
        info_data = await _fetch_me_info(shop_token=shop_token)
    except FanbookSignError as exc:
        if not exc.is_auth_error and exc.code not in _SHOP_TOKEN_INVALID_CODES:
            raise
        if fb_user_id:
            _shop_token_cache.delete(fb_user_id)
        shop_token = await _exchange_shop_token(fb_user_id=fb_user_id, sign_token=sign_token)
        info_data = await _fetch_me_info(shop_token=shop_token)

    return info_data.point
