"""Dakanu 共享异步 HTTP 客户端、错误映射与模型校验工具。"""

from __future__ import annotations

import math
import asyncio
from typing import Any, Literal, TypeVar
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from collections.abc import Mapping

import httpx
from pydantic import BaseModel, ValidationError

from gsuid_core.logger import logger

BASE_URL = "https://www.dakanu.com"
_DEFAULT_TIMEOUT = 30.0
_CLIENT_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)

_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None

ModelT = TypeVar("ModelT", bound=BaseModel)


class DakanuError(Exception):
    """Dakanu 请求失败，message 可直接向用户说明原因。"""


def get_dakanu_client() -> httpx.AsyncClient:
    """懒创建并复用当前事件循环下的 Dakanu 共享异步连接池。"""
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is not None and not _client.is_closed and _client_loop is loop:
        return _client
    _client = httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=httpx.Timeout(_DEFAULT_TIMEOUT),
        follow_redirects=True,
        limits=_CLIENT_LIMITS,
    )
    _client_loop = loop
    return _client


async def close_dakanu_client() -> None:
    """停机或热重载时关闭共享异步连接池。"""
    global _client, _client_loop
    client = _client
    _client = None
    _client_loop = None
    if client is not None and not client.is_closed:
        await client.aclose()


def parse_retry_after_seconds(response: httpx.Response) -> int | None:
    """从 429 响应头解析 Retry-After 等待秒数；无法解析时返回 None。"""
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    cleaned = raw.strip()
    try:
        seconds = float(cleaned)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(cleaned)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        delta = (retry_at - datetime.now(timezone.utc)).total_seconds()
        return max(1, math.ceil(delta)) if delta > 0 else None
    if not math.isfinite(seconds) or seconds <= 0:
        return None
    return max(1, math.ceil(seconds))


def format_rate_limit_message(response: httpx.Response, *, prefix: str = "查询过于频繁") -> str:
    """构造带 Retry-After 提示的限流文案。"""
    wait_seconds = parse_retry_after_seconds(response)
    if wait_seconds is not None:
        return f"{prefix}，请约 {wait_seconds} 秒后再试。"
    return f"{prefix}，请稍后再试。"


def safe_error_text(response: httpx.Response) -> str | None:
    """提取非 HTML 的安全 JSON error 文案，防止把上游错误页展示给用户。"""
    try:
        payload: Any = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    err = payload.get("error")
    if not isinstance(err, str):
        return None
    cleaned = err.strip()
    if not cleaned or "<" in cleaned:
        return None
    return cleaned


async def request_raw(
    method: Literal["GET", "POST"],
    path: str,
    *,
    params: Mapping[str, str | int] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float | None = None,
    ephemeral: bool = False,
) -> httpx.Response:
    """发送单次异步 HTTP 请求；ephemeral=True 时使用独立短生命周期客户端隔离 Cookie。"""
    request_timeout = httpx.Timeout(timeout) if timeout is not None else httpx.USE_CLIENT_DEFAULT
    if ephemeral:
        async with httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(timeout if timeout is not None else _DEFAULT_TIMEOUT),
            follow_redirects=True,
        ) as client:
            return await client.request(method, path, params=params, headers=headers)
    client = get_dakanu_client()
    return await client.request(method, path, params=params, headers=headers, timeout=request_timeout)


async def request_json(
    method: Literal["GET", "POST"],
    path: str,
    *,
    params: Mapping[str, str | int] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float | None = None,
    log_tag: str,
    label: str,
    ok_statuses: frozenset[int] = frozenset({200}),
    empty_statuses: frozenset[int] = frozenset(),
    status_messages: Mapping[int, str] | None = None,
    rate_limit_prefix: str = "查询过于频繁",
    upstream_error_msg: str | None = None,
    fallback_error_msg: str | None = None,
    invalid_json_msg: str | None = None,
    network_error_msg: str | None = None,
    timeout_error_msg: str | None = None,
) -> Any:
    """统一发送异步 JSON 请求并把 HTTP/网络/格式异常映射为 DakanuError。"""
    try:
        response = await request_raw(method, path, params=params, headers=headers, timeout=timeout)
    except httpx.TimeoutException:
        logger.warning(f"{log_tag} 请求{label}超时")
        raise DakanuError(timeout_error_msg or network_error_msg or f"请求{label}失败，请稍后再试。") from None
    except httpx.HTTPError as exc:
        logger.warning(f"{log_tag} 请求{label}失败：{exc}")
        raise DakanuError(network_error_msg or f"请求{label}失败，请稍后再试。") from None

    code = response.status_code
    if code in empty_statuses:
        return None
    if code == 429:
        raise DakanuError(format_rate_limit_message(response, prefix=rate_limit_prefix))
    if status_messages and code in status_messages:
        raise DakanuError(status_messages[code])
    if code in {204, 404}:
        raise DakanuError(f"暂无{label}数据，请稍后再试。")
    if code in {502, 503, 504}:
        raise DakanuError(upstream_error_msg or f"战绩站暂时无法读取{label}，请稍后再试。")
    if code not in ok_statuses:
        logger.warning(f"{log_tag} 读取{label}返回 HTTP {code}")
        raise DakanuError(fallback_error_msg or f"读取{label}失败，请稍后再试。")

    try:
        return response.json()
    except ValueError:
        logger.warning(f"{log_tag} {label}返回非 JSON 响应")
        raise DakanuError(invalid_json_msg or f"{label}数据格式异常，请稍后再试。") from None


def parse_model(
    model_cls: type[ModelT],
    payload: Any,
    *,
    log_tag: str,
    label: str,
    error_msg: str | None = None,
) -> ModelT:
    """使用 Pydantic 校验响应载荷；校验失败时记日志并抛出 DakanuError。"""
    try:
        return model_cls.model_validate(payload)
    except ValidationError as exc:
        logger.warning(f"{log_tag} {label}响应结构异常：{exc.error_count()} 处校验失败")
        raise DakanuError(error_msg or f"{label}数据格式异常，请稍后再试。") from None
