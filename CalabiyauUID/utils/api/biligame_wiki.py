"""Biligame 卡拉彼丘 Wiki 活动公开读取接口。"""

from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

import httpx

from gsuid_core.logger import logger

_WIKI_API_URL = "https://wiki.biligame.com/klbq/api.php"
_WIKI_REFERER = "https://wiki.biligame.com/klbq/%E6%B4%BB%E5%8A%A8"
_WIKI_CDKEY_REFERER = "https://wiki.biligame.com/klbq/%E5%85%91%E6%8D%A2%E7%A0%81"
_WIKI_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": _WIKI_REFERER,
}
_BEIJING_TZ = timezone(timedelta(hours=8))
_IMAGEINFO_BATCH_SIZE = 50
_LOG_TAG = "[卡拉彼丘·活动查询]"
_CDKEY_LOG_TAG = "[卡拉彼丘·兑换码]"


class WikiError(RuntimeError):
    """Biligame Wiki 接口请求或解析失败。"""


@dataclass(frozen=True)
class WikiRawActivity:
    """从 SMW ask 接口解析出的原始活动条目。"""

    title: str
    image_name: str
    start_at: datetime
    end_at: datetime
    summary: str
    page_url: str


@dataclass(frozen=True)
class WikiActivityItem:
    """补全封面直链后的进行中活动条目。"""

    title: str
    image_name: str
    image_url: str
    start_at: datetime
    end_at: datetime
    summary: str
    page_url: str
    is_permanent: bool


@dataclass(frozen=True)
class WikiRedeemCodeItem:
    """从 SMW ask 接口解析出的兑换码条目。"""

    code: str
    rewards: str
    expires_at: datetime
    is_permanent: bool


def beijing_now() -> datetime:
    """返回当前北京时间（UTC+8）。"""
    return datetime.now(_BEIJING_TZ)


def parse_smw_beijing_time(item: object) -> datetime | None:
    """解析 SMW 日期对象；Wiki 把北京时间按 UTC 纪元存储，不可额外加 8 小时。"""
    if not isinstance(item, dict):
        return None
    if "timestamp" in item:
        raw_ts = item["timestamp"]
        if isinstance(raw_ts, int) and not isinstance(raw_ts, bool):
            return datetime.fromtimestamp(raw_ts, timezone.utc).replace(tzinfo=_BEIJING_TZ)
        if isinstance(raw_ts, str):
            stripped = raw_ts.strip()
            if stripped.lstrip("-").isdigit():
                return datetime.fromtimestamp(int(stripped), timezone.utc).replace(tzinfo=_BEIJING_TZ)
    if "raw" in item and isinstance(item["raw"], str):
        parts = item["raw"].split("/")
        if len(parts) >= 7 and all(part.isdigit() for part in parts[1:7]):
            year, month, day, hour, minute, second = (int(part) for part in parts[1:7])
            return datetime(year, month, day, hour, minute, second, tzinfo=_BEIJING_TZ)
    return None


def _first_nonempty_str(printouts: dict[object, object], key: str) -> str | None:
    if key not in printouts:
        return None
    values = printouts[key]
    if not isinstance(values, list) or not values:
        return None
    first = values[0]
    if not isinstance(first, str):
        return None
    cleaned = first.strip()
    return cleaned if cleaned else None


def _first_time(printouts: dict[object, object], key: str) -> datetime | None:
    if key not in printouts:
        return None
    values = printouts[key]
    if not isinstance(values, list) or not values:
        return None
    return parse_smw_beijing_time(values[0])


def _extract_ask_results(payload: object) -> dict[object, object]:
    if not isinstance(payload, dict) or "query" not in payload:
        return {}
    query_obj = payload["query"]
    if not isinstance(query_obj, dict) or "results" not in query_obj:
        return {}
    results = query_obj["results"]
    return results if isinstance(results, dict) else {}


def parse_ask_activities(payload: object) -> list[WikiRawActivity]:
    """解析 SMW action=ask 返回的活动列表。"""
    results = _extract_ask_results(payload)
    if not results:
        return []

    items: list[WikiRawActivity] = []
    for page_key, entry in results.items():
        if not isinstance(entry, dict) or "printouts" not in entry:
            continue
        printouts = entry["printouts"]
        if not isinstance(printouts, dict):
            continue
        start_at = _first_time(printouts, "活动开始时间")
        end_at = _first_time(printouts, "活动结束时间")
        if start_at is None or end_at is None:
            continue

        title = _first_nonempty_str(printouts, "活动名")
        if title is None:
            if "fulltext" in entry and isinstance(entry["fulltext"], str) and entry["fulltext"].strip():
                title = entry["fulltext"].strip()
            elif isinstance(page_key, str) and page_key.strip():
                title = page_key.strip()
            else:
                continue

        image_name = _first_nonempty_str(printouts, "活动图片") or ""
        summary = _first_nonempty_str(printouts, "活动简介") or ""
        page_url = entry["fullurl"].strip() if "fullurl" in entry and isinstance(entry["fullurl"], str) else ""
        items.append(
            WikiRawActivity(
                title=title,
                image_name=image_name,
                start_at=start_at,
                end_at=end_at,
                summary=summary,
                page_url=page_url,
            )
        )
    return items


def parse_ask_redeem_codes(payload: object) -> list[WikiRedeemCodeItem]:
    """解析 SMW action=ask 返回的兑换码列表。"""
    results = _extract_ask_results(payload)
    if not results:
        return []

    items: list[WikiRedeemCodeItem] = []
    for entry in results.values():
        if not isinstance(entry, dict) or "printouts" not in entry:
            continue
        printouts = entry["printouts"]
        if not isinstance(printouts, dict):
            continue
        code = _first_nonempty_str(printouts, "兑换码")
        expires_at = _first_time(printouts, "兑换码失效时间")
        if code is None or expires_at is None:
            continue
        rewards = _first_nonempty_str(printouts, "奖励内容") or ""
        items.append(
            WikiRedeemCodeItem(
                code=code,
                rewards=rewards,
                expires_at=expires_at,
                is_permanent=expires_at.year >= 2099,
            )
        )
    return items


def parse_imageinfo_urls(payload: object) -> dict[str, str]:
    """解析 MediaWiki imageinfo 返回的 文件名 -> CDN 直链映射。"""
    if not isinstance(payload, dict) or "query" not in payload:
        return {}
    query_obj = payload["query"]
    if not isinstance(query_obj, dict) or "pages" not in query_obj:
        return {}
    pages = query_obj["pages"]
    if not isinstance(pages, dict):
        return {}

    urls: dict[str, str] = {}
    for page in pages.values():
        if not isinstance(page, dict) or "title" not in page or "imageinfo" not in page:
            continue
        raw_title = page["title"]
        info_list = page["imageinfo"]
        if not isinstance(raw_title, str) or not isinstance(info_list, list) or not info_list:
            continue
        first_info = info_list[0]
        if not isinstance(first_info, dict) or "url" not in first_info:
            continue
        raw_url = first_info["url"]
        if not isinstance(raw_url, str) or not raw_url.strip():
            continue
        file_name = raw_title.split(":", 1)[-1].strip()
        if file_name:
            urls[file_name] = raw_url.strip()
    return urls


async def _request_wiki_json(
    client: httpx.AsyncClient,
    params: dict[str, str],
    *,
    log_tag: str = _LOG_TAG,
    subject: str = "Wiki 活动数据",
) -> object:
    try:
        response = await client.get(_WIKI_API_URL, params=params)
    except httpx.HTTPError as exc:
        logger.warning(f"{log_tag} 请求 Biligame Wiki 失败：{exc}")
        raise WikiError(f"获取 {subject} 失败，请稍后再试。") from None

    if response.status_code in {429, 567}:
        logger.warning(f"{log_tag} Biligame Wiki 返回限流状态 HTTP {response.status_code}")
        raise WikiError("Wiki 查询过于频繁，请稍后再试。")
    if response.status_code in {502, 503, 504}:
        logger.warning(f"{log_tag} Biligame Wiki 上游异常 HTTP {response.status_code}")
        raise WikiError("Wiki 服务暂时不可用，请稍后再试。")
    if response.status_code != 200:
        logger.warning(f"{log_tag} Biligame Wiki 返回异常状态 HTTP {response.status_code}")
        raise WikiError(f"获取 {subject} 失败，请稍后再试。")

    try:
        return response.json()
    except ValueError:
        logger.warning(f"{log_tag} Biligame Wiki 返回非 JSON 响应")
        raise WikiError(f"{subject}格式异常，请稍后再试。") from None


async def fetch_ongoing_activities(now: datetime | None = None) -> list[WikiActivityItem]:
    """获取当前正在进行中的活动列表（含常驻活动与封面直链）。"""
    current = now.astimezone(_BEIJING_TZ) if now is not None else beijing_now()
    # 按前一天起算做服务端粗筛，避免凌晨边界被 SMW 日期截断
    cutoff_date = (current - timedelta(days=1)).strftime("%Y-%m-%d")
    ask_query = (
        f"[[分类:活动]][[活动结束时间::≥{cutoff_date}]]"
        "|?活动名|?活动图片|?活动开始时间|?活动结束时间|?活动简介"
        "|sort=活动开始时间|order=asc|limit=100"
    )

    async with httpx.AsyncClient(
        headers=_WIKI_HEADERS,
        timeout=20.0,
        follow_redirects=True,
    ) as client:
        ask_payload = await _request_wiki_json(
            client,
            {
                "action": "ask",
                "query": ask_query,
                "format": "json",
            },
        )
        raw_items = parse_ask_activities(ask_payload)
        ongoing_raw = [item for item in raw_items if item.start_at <= current <= item.end_at]
        if not ongoing_raw:
            return []

        unique_images = list(dict.fromkeys(item.image_name for item in ongoing_raw if item.image_name))
        image_urls: dict[str, str] = {}
        for offset in range(0, len(unique_images), _IMAGEINFO_BATCH_SIZE):
            batch = unique_images[offset : offset + _IMAGEINFO_BATCH_SIZE]
            titles = "|".join(f"File:{name}" for name in batch)
            info_payload = await _request_wiki_json(
                client,
                {
                    "action": "query",
                    "titles": titles,
                    "prop": "imageinfo",
                    "iiprop": "url",
                    "format": "json",
                },
            )
            image_urls.update(parse_imageinfo_urls(info_payload))

    return [
        WikiActivityItem(
            title=item.title,
            image_name=item.image_name,
            image_url=image_urls[item.image_name] if item.image_name in image_urls else "",
            start_at=item.start_at,
            end_at=item.end_at,
            summary=item.summary,
            page_url=item.page_url,
            is_permanent=item.end_at.year >= 2099,
        )
        for item in ongoing_raw
    ]


async def fetch_active_redeem_codes(now: datetime | None = None) -> list[WikiRedeemCodeItem]:
    """获取当前未失效的兑换码列表（2099 年占位时间视为常驻）。"""
    current = now.astimezone(_BEIJING_TZ) if now is not None else beijing_now()
    # 按前一天起算做服务端粗筛，避免凌晨边界被 SMW 日期截断
    cutoff_date = (current - timedelta(days=1)).strftime("%Y-%m-%d")
    ask_query = (
        f"[[兑换码::+]][[兑换码失效时间::≥{cutoff_date}]]"
        "|?兑换码|?奖励内容|?兑换码失效时间"
        "|sort=兑换码失效时间|order=asc|limit=100"
    )

    async with httpx.AsyncClient(
        headers={**_WIKI_HEADERS, "Referer": _WIKI_CDKEY_REFERER},
        timeout=20.0,
        follow_redirects=True,
    ) as client:
        ask_payload = await _request_wiki_json(
            client,
            {
                "action": "ask",
                "query": ask_query,
                "format": "json",
            },
            log_tag=_CDKEY_LOG_TAG,
            subject="Wiki 兑换码数据",
        )
    raw_items = parse_ask_redeem_codes(ask_payload)
    return [item for item in raw_items if item.is_permanent or current <= item.expires_at]
