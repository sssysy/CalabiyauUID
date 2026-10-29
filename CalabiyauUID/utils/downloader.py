"""插件资源下载缓存。"""

import hashlib
from pathlib import Path
from collections.abc import Sequence

from gsuid_core.utils.download_resource.download_file import download as download_file

from .utils.paths import DATA_DIR

IMG_CACHE_DIR: Path = DATA_DIR / "img_cache"
IMG_CACHE_DIR.mkdir(parents=True, exist_ok=True)

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
