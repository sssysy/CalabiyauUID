"""插件资源下载缓存。"""

import hashlib
from pathlib import Path
from dataclasses import dataclass
from collections.abc import Sequence

import httpx

from gsuid_core.utils.download_resource.download_file import download as download_file

from .utils.paths import DATA_DIR

IMG_CACHE_DIR: Path = DATA_DIR / "img_cache"
IMG_CACHE_DIR.mkdir(parents=True, exist_ok=True)

REPLAY_CACHE_DIR: Path = DATA_DIR / "cache" / "replay"
REPLAY_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})


def _image_suffix(url: str) -> str:
    suffix = Path(url.split("?")[0].split("#")[0]).suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return suffix
    return ".webp"


def image_cache_path(url: str) -> Path:
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()
    return IMG_CACHE_DIR / f"{digest}{_image_suffix(url)}"


async def download_image(url: str) -> Path | None:
    """把远程图片写入 img_cache；失败返回 None。"""
    if not url:
        return None
    target = image_cache_path(url)
    if target.is_file() and target.stat().st_size > 0:
        return target
    retcode = await download_file(url, IMG_CACHE_DIR, target.name, tag="[卡拉彼丘·资源缓存]")
    if retcode != 200 or not target.is_file() or target.stat().st_size <= 0:
        return None
    return target


async def resolve_image(url: str, local_path: Path | None = None) -> Path | None:
    """优先返回本地素材，缺失时回退远程缓存。"""
    if local_path is not None and local_path.is_file() and local_path.stat().st_size > 0:
        return local_path
    if not url:
        return None
    return await download_image(url)


async def download_images(urls: Sequence[str]) -> list[Path | None]:
    """按固定顺序返回图片缓存路径；单张失败不打断其它图片。"""
    paths: list[Path | None] = []
    for url in urls:
        paths.append(await download_image(url))
    return paths


async def download_to_dir(
    url: str,
    target_dir: Path,
    filename: str,
    *,
    tag: str = "[卡拉彼丘·资源下载]",
) -> Path | None:
    """复用框架下载器把远程文件写入指定目录；失败返回 None。"""
    if not url or not filename:
        return None
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    async with httpx.AsyncClient(timeout=30.0) as client:
        retcode = await download_file(url, target_dir, filename, sess=client, tag=tag)
    if retcode != 200 or not target.is_file() or target.stat().st_size <= 0:
        return None
    return target


@dataclass(frozen=True, slots=True)
class ReplayDownloadResult:
    path: Path | None
    status_code: int | None


def replay_cache_path(room_id: str) -> Path:
    """返回指定对局回放在本地缓存中的目标路径。"""
    return REPLAY_CACHE_DIR / f"dakanu.com_{room_id}.replay"


def find_cached_replay(room_id: str) -> Path | None:
    """命中本地非空回放缓存时返回路径，否则返回 None。"""
    target = replay_cache_path(room_id)
    if target.is_file() and target.stat().st_size > 0:
        return target
    return None


async def download_replay(
    room_id: str,
    url: str,
    cookies: dict[str, str],
) -> ReplayDownloadResult:
    """携带临时 Cookie 下载对局回放文件到 cache/replay/。"""
    if not url or not room_id:
        return ReplayDownloadResult(path=None, status_code=None)
    REPLAY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = replay_cache_path(room_id)
    async with httpx.AsyncClient(cookies=cookies, timeout=120.0, follow_redirects=True) as client:
        raw_retcode: object = await download_file(
            url,
            REPLAY_CACHE_DIR,
            target.name,
            sess=client,
            tag="[卡拉彼丘·回放下载]",
        )
    status_code = raw_retcode if isinstance(raw_retcode, int) and not isinstance(raw_retcode, bool) else None
    if status_code == 200 and target.is_file() and target.stat().st_size > 0:
        return ReplayDownloadResult(path=target, status_code=200)
    return ReplayDownloadResult(path=None, status_code=status_code)
