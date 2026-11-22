"""Fanbook 卡拉彼丘官方社群每日签到小程序 HTTP 客户端。"""

from __future__ import annotations

import json
import time
import asyncio
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

import httpx

from gsuid_core.logger import logger

_SIGN_API_BASE = "https://open.fanbook.cn/mp/138519745866498048/368331042878263296/sign/api"
_SIGN_REFERER = (
    "https://open.fanbook.cn/mp/138519745866498048/368331042878263296/sign/"
    "?enter_type=message_card&view=1&fb_redirect&open_type=mp"
)
_SIGN_APP_KEY = "z2cg4sg3vokll9pydc5d"
_SIGN_APP_SECRET = "f8f8zvnzi87tuy27cweb"
_NONCE_ALPHABET = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"
CALABIYAU_GUILD_ID = "167099262725787648"
CALABIYAU_SIGN_CHANNEL_ID = "408518973252960256"
_QUERY_MAX_ATTEMPTS = 12
_QUERY_RETRY_DELAY_S = 0.5
_CODE_NOT_SIGNED_YET = 70000
_BEIJING_TZ = timezone(timedelta(hours=8))
_LOG_TAG = "[卡拉彼丘·Fanbook签到]"


class FanbookSignError(RuntimeError):
    """Fanbook 签到小程序接口调用或业务失败。"""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class FanbookSignResult:
    """Fanbook 每日签到结果详情。"""

    score: int
    rank: int
    sum_sign_days: int
    continuous_sign_days: int
    shop_point: int
    sign_date_time: str
    reply_text: str
    already_signed: bool = False


def beijing_today_str() -> str:
    """返回北京时间 YYYY-MM-DD 日期字符串。"""
    return datetime.now(_BEIJING_TZ).strftime("%Y-%m-%d")


def _generate_nonce(length: int = 20) -> str:
    return "".join(secrets.choice(_NONCE_ALPHABET) for _ in range(length))


def _build_get_headers(params: dict[str, str]) -> dict[str, str]:
    nonce = _generate_nonce()
    timestamp_ms = str(int(time.time() * 1000))
    query_suffix = "".join(f"&{key}={val}" for key, val in params.items())
    raw = f"{_SIGN_APP_SECRET}&AppKey={_SIGN_APP_KEY}&Nonce={nonce}&Timestamp={timestamp_ms}{query_suffix}&{_SIGN_APP_SECRET}"
    signature = hashlib.md5(raw.encode("utf-8")).hexdigest().lower()
    return {
        "AppKey": _SIGN_APP_KEY,
        "Nonce": nonce,
        "Timestamp": timestamp_ms,
        "Signature": signature,
        "Content-Type": "application/json",
        "Origin": "https://open.fanbook.cn",
        "Referer": _SIGN_REFERER,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    }


def _build_post_headers_and_body(payload: dict[str, str]) -> tuple[dict[str, str], str]:
    nonce = _generate_nonce()
    timestamp_ms = str(int(time.time() * 1000))
    body_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    raw = (
        f"{_SIGN_APP_SECRET}&AppKey={_SIGN_APP_KEY}&Nonce={nonce}"
        f"&Timestamp={timestamp_ms}&requestBody={body_str}&{_SIGN_APP_SECRET}"
    )
    signature = hashlib.md5(raw.encode("utf-8")).hexdigest().lower()
    headers = {
        "AppKey": _SIGN_APP_KEY,
        "Nonce": nonce,
        "Timestamp": timestamp_ms,
        "Signature": signature,
        "Content-Type": "application/json",
        "Origin": "https://open.fanbook.cn",
        "Referer": _SIGN_REFERER,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    }
    return headers, body_str


def _read_int(payload: dict[str, object], key: str, default: int = 0) -> int:
    if key not in payload:
        return default
    value = payload[key]
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default


def _read_str(payload: dict[str, object], key: str, default: str = "") -> str:
    if key not in payload:
        return default
    value = payload[key]
    if isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return default


async def _request_sign_api(
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    payload: dict[str, str] | None = None,
    sign_token: str = "",
) -> dict[str, object]:
    url = f"{_SIGN_API_BASE}{path}"
    cookies = {"token": sign_token} if sign_token else None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0), cookies=cookies) as client:
            if method == "GET":
                query_params = params if params is not None else {}
                headers = _build_get_headers(query_params)
                response = await client.get(url, params=query_params, headers=headers)
            else:
                body_payload = payload if payload is not None else {}
                headers, body_str = _build_post_headers_and_body(body_payload)
                response = await client.post(url, content=body_str.encode("utf-8"), headers=headers)
    except httpx.HTTPError as exc:
        logger.warning(f"{_LOG_TAG} 请求 {path} 网络异常：{exc}")
        raise FanbookSignError("Fanbook 签到服务连接失败，请稍后重试。") from exc

    if response.status_code >= 400:
        logger.warning(f"{_LOG_TAG} 请求 {path} 返回 HTTP {response.status_code}")
        raise FanbookSignError(f"Fanbook 签到接口异常（HTTP {response.status_code}）。")

    try:
        parsed: object = response.json()
    except ValueError as exc:
        logger.warning(f"{_LOG_TAG} 解析 {path} JSON 失败：{exc}")
        raise FanbookSignError("Fanbook 签到接口返回了无效数据。") from exc

    if not isinstance(parsed, dict):
        raise FanbookSignError("Fanbook 签到接口响应格式异常。")

    raw_code = parsed["code"] if "code" in parsed else None
    code = raw_code if isinstance(raw_code, int) and not isinstance(raw_code, bool) else None
    raw_msg = parsed["msg"] if "msg" in parsed else None
    msg = raw_msg if isinstance(raw_msg, str) and raw_msg else "签到请求失败"
    if code != 0:
        logger.warning(f"{_LOG_TAG} 接口 {path} 业务返回 code={code} msg={msg}")
        raise FanbookSignError(msg, code=code)
    return parsed


def _parse_sign_result(data_obj: object, *, already_signed: bool = False) -> FanbookSignResult | None:
    if not isinstance(data_obj, dict):
        return None
    sign_info_obj = data_obj["signInfo"] if "signInfo" in data_obj else None
    user_info_obj = data_obj["userInfo"] if "userInfo" in data_obj else None
    if not isinstance(sign_info_obj, dict):
        return None

    shop_point = _read_int(user_info_obj, "shopPoint") if isinstance(user_info_obj, dict) else 0
    replays_obj = sign_info_obj["replays"] if "replays" in sign_info_obj else None
    reply_text = ""
    if isinstance(replays_obj, list) and replays_obj and isinstance(replays_obj[0], str):
        reply_text = replays_obj[0]

    return FanbookSignResult(
        score=_read_int(sign_info_obj, "score"),
        rank=_read_int(sign_info_obj, "rank"),
        sum_sign_days=_read_int(sign_info_obj, "sumSignDays"),
        continuous_sign_days=_read_int(sign_info_obj, "continuousSignDays"),
        shop_point=shop_point,
        sign_date_time=_read_str(sign_info_obj, "signDateTime"),
        reply_text=reply_text,
        already_signed=already_signed,
    )


def _build_user_payload(fb_user_id: str, fb_short_id: str) -> dict[str, str]:
    return {
        "channelId": CALABIYAU_SIGN_CHANNEL_ID,
        "guildId": CALABIYAU_GUILD_ID,
        "longUid": fb_user_id,
        "shortUid": fb_short_id,
    }


async def get_gain_point_able() -> int:
    """查询当前社区每日签到可获得的基础积分数。"""
    parsed = await _request_sign_api("GET", "/open/getGainPointAble", params={"guild": CALABIYAU_GUILD_ID})
    data_obj = parsed["data"] if "data" in parsed else None
    if isinstance(data_obj, int) and not isinstance(data_obj, bool):
        return data_obj
    return 0


async def query_sign_result(
    *,
    fb_user_id: str,
    fb_short_id: str,
    sign_token: str = "",
    already_signed: bool = False,
) -> FanbookSignResult | None:
    """查询指定用户的每日签到结果。"""
    try:
        parsed = await _request_sign_api(
            "POST",
            "/open/querySignResult",
            payload=_build_user_payload(fb_user_id, fb_short_id),
            sign_token=sign_token,
        )
    except FanbookSignError as exc:
        if exc.code == _CODE_NOT_SIGNED_YET:
            return None
        raise
    data_obj = parsed["data"] if "data" in parsed else None
    return _parse_sign_result(data_obj, already_signed=already_signed)


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
