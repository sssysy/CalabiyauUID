"""卡拉彼丘表情包随机抽取与目录解析服务。"""

import random
from pathlib import Path
from dataclasses import dataclass

from gsuid_core.pool import to_thread
from gsuid_core.logger import logger

from ..utils.helper.maps import resolve_role_alias, get_role_display_names
from ..utils.utils.paths import STICKER_DIR

_LOG_TAG = "[卡拉彼丘·表情包]"
_IMAGE_SUFFIXES: frozenset[str] = frozenset({".png", ".gif", ".jpg", ".jpeg", ".webp"})
_USAGE_TEXT = "用法：kq抽表情 [角色名] 或 kq表情包 [角色名]"


@dataclass(frozen=True)
class StickerResult:
    image: bytes | None
    error: str | None


def parse_sticker_query(raw_text: str) -> tuple[str, str | None]:
    """按空格切分表情包命令参数，支持留空或单个角色名。"""
    tokens = raw_text.strip().split()
    if not tokens:
        return "", None
    if len(tokens) > 1:
        return "", _USAGE_TEXT
    return tokens[0], None


def _is_hidden_name(name: str) -> bool:
    return name.startswith("_") or name.startswith(".")


def _is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES


def _collect_images_in_dir(directory: Path) -> list[Path]:
    images: list[Path] = []
    for item in directory.rglob("*"):
        if not _is_image_file(item):
            continue
        rel_parts = item.relative_to(directory).parts
        if any(_is_hidden_name(part) for part in rel_parts[:-1]):
            continue
        images.append(item)
    return images


def _collect_all_images(sticker_dir: Path) -> list[Path]:
    images: list[Path] = []
    for entry in sticker_dir.iterdir():
        if _is_hidden_name(entry.name):
            continue
        if _is_image_file(entry):
            images.append(entry)
        elif entry.is_dir():
            images.extend(_collect_images_in_dir(entry))
    return images


def _resolve_role_dir(query: str, sticker_dir: Path) -> tuple[str | None, Path | None]:
    role_id = resolve_role_alias(query)
    if role_id is None:
        return None, None
    display_names = get_role_display_names()
    if role_id not in display_names:
        return None, None
    role_name = display_names[role_id]
    return role_name, sticker_dir / role_name


def _pick_sticker_path(query: str) -> tuple[Path | None, str | None]:
    if not STICKER_DIR.is_dir():
        return None, "表情包资源目录不存在，请先同步资源后再试。"

    if not query:
        images = _collect_all_images(STICKER_DIR)
        if not images:
            return None, "当前表情包库暂无可用表情。"
        return random.choice(images), None

    role_name, role_dir = _resolve_role_dir(query, STICKER_DIR)
    if role_name is None or role_dir is None:
        return None, f"未找到角色「{query}」，请检查角色名后重试。"
    if not role_dir.is_dir():
        return None, f"角色「{role_name}」暂无可用表情包。"

    images = _collect_images_in_dir(role_dir)
    if not images:
        return None, f"角色「{role_name}」暂无可用表情包。"
    return random.choice(images), None


def _read_sticker_sync(query: str) -> StickerResult:
    sticker_path, error = _pick_sticker_path(query)
    if error is not None or sticker_path is None:
        return StickerResult(image=None, error=error or "当前表情包库暂无可用表情。")

    try:
        data = sticker_path.read_bytes()
    except OSError:
        logger.exception(f"{_LOG_TAG} 读取表情包文件失败：{sticker_path}")
        return StickerResult(image=None, error="读取表情包文件失败，请稍后再试。")

    if not data:
        logger.warning(f"{_LOG_TAG} 表情包文件为空：{sticker_path}")
        return StickerResult(image=None, error="表情包文件异常，请稍后再试。")
    return StickerResult(image=data, error=None)


async def get_random_sticker(query: str) -> StickerResult:
    """随机或按角色抽取一张表情包并返回原始图片字节。"""
    return await to_thread(_read_sticker_sync)(query)
