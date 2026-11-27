"""资源仓库中的本地素材路径。"""

import base64
from pathlib import Path

from gsuid_core.pool import to_thread

from ..utils.paths import DATA_DIR, ASSET_DIR, CUSTOM_BG_PATH
from ...calabiyau_config import CalabiyauConfig

_IMAGE_SUFFIXES = (".webp", ".png", ".jpg", ".jpeg", ".gif")
_BUNDLED_BANNER_BG = Path(__file__).resolve().parents[2] / "calabiyau_help" / "texture2d" / "banner_bg.jpg"


def _existing_image(path: Path) -> Path | None:
    if path.is_file() and path.stat().st_size > 0:
        return path
    return None


def _image_with_suffix(stem: Path) -> Path | None:
    for suffix in _IMAGE_SUFFIXES:
        found = _existing_image(stem.with_suffix(suffix))
        if found is not None:
            return found
    return None


def _local_id_image(directory: str, asset_id: int, *subdirs: str) -> Path | None:
    base = ASSET_DIR / directory
    for subdir in subdirs:
        found = _image_with_suffix(base / subdir / str(asset_id))
        if found is not None:
            return found
    return _image_with_suffix(base / str(asset_id))


def local_avatar_image(avatar_id: int) -> Path | None:
    """按头像 ID 查找本地头像。"""
    return _local_id_image("avatars", avatar_id)


def local_chat_emote_image(emote_id: str) -> Path | None:
    """按聊天表情 ID 查找本地表情。"""
    cleaned = emote_id.strip().lstrip("#")
    if not cleaned.isascii() or not cleaned.isdigit():
        return None
    return _image_with_suffix(ASSET_DIR / "chat-emotes" / cleaned)


def local_baseplate_image(avatar_id: int) -> Path | None:
    """头像底图与头像共用 avatarId。"""
    return _local_id_image("baseplates-lg", avatar_id)


def local_frame_image(border_id: int) -> Path | None:
    """头像框使用接口里的 borderId。"""
    return _local_id_image("frames-pc", border_id)


def local_role_image(role_id: int) -> Path | None:
    """角色立绘使用接口里的 roleId。"""
    return _local_id_image("roles", role_id, "by-id")


def local_map_image(map_id: int) -> Path | None:
    """地图使用接口里的 mapId。"""
    return _local_id_image("maps", map_id, "by-id")


def local_map_slug_image(slug: str) -> Path | None:
    """地图宽图使用站点 slug，例如 map-01。"""
    return _image_with_suffix(ASSET_DIR / "maps" / slug)


def local_medal_image(medal_id: int) -> Path | None:
    """勋章使用接口里的 medals[].id。"""
    return _local_id_image("medals", medal_id)


def local_spray_image(spray_id: int) -> Path | None:
    """喷漆使用接口返回的喷漆 ID。"""
    return _local_id_image("sprays", spray_id)


def local_card_image(card_id: int) -> Path | None:
    """个性名片使用接口返回的名片 ID。"""
    return _local_id_image("cards", card_id)


def local_frame_index_image(frame_id: int) -> Path | None:
    """旧版头像框资源使用接口返回的 frame ID。"""
    return _local_id_image("frames", frame_id)


def local_tier_image(tier_index: int) -> Path | None:
    return _image_with_suffix(ASSET_DIR / "tiers" / f"tier-{tier_index}")


def local_challenge_tier_image(tier_index: int) -> Path | None:
    return _image_with_suffix(ASSET_DIR / "challenge-rank" / f"tier-{tier_index}")


def local_sticker_image(sticker_id: int) -> Path | None:
    return _image_with_suffix(ASSET_DIR / "stickers" / f"sticker_{sticker_id:02d}")


def local_faction_image(camp_code: int) -> Path | None:
    return _image_with_suffix(ASSET_DIR / "factions" / f"camp-{camp_code}-thumb")


def local_position_icon(position_code: int) -> Path | None:
    path = ASSET_DIR / "factions" / f"position-{position_code}.svg"
    return _existing_image(path)


def local_banner_bg_image() -> Path | None:
    """优先读取 data 下热更新后的 banner_bg，缺失时回退插件内置底图。"""
    synced_path = DATA_DIR / "help" / "texture2d" / "banner_bg.jpg"
    found = _existing_image(synced_path)
    if found is not None:
        return found
    return _existing_image(_BUNDLED_BANNER_BG)


def local_card_bg_image() -> Path | None:
    """优先读取自定义背景 bg.png，未设置时回退赛季高斯模糊背景 bg_blur.jpg。"""
    cfg_raw = CalabiyauConfig.get_config("CustomBgPath").data
    if isinstance(cfg_raw, str) and cfg_raw.strip():
        configured = _existing_image(Path(cfg_raw.strip()))
        if configured is not None:
            return configured
    custom = _existing_image(CUSTOM_BG_PATH)
    if custom is not None:
        return custom
    blur_path = DATA_DIR / "help" / "texture2d" / "bg_blur.jpg"
    found_blur = _existing_image(blur_path)
    if found_blur is not None:
        return found_blur
    from ...calabiyau_help.help_services import ensure_help_textures

    ensure_help_textures()
    return _existing_image(blur_path)


def load_card_bg_data_uri() -> str:
    """读取当前生效的卡片背景图并编码为 data URI。"""
    path = local_card_bg_image()
    if path is None:
        return ""
    return image_data_uri(path.read_bytes(), path.suffix)


def image_data_uri(content: bytes, suffix: str) -> str:
    """把图片字节编码成 pytakumi 可读取的 data URI。"""
    mime_types: dict[str, str] = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    normalized = suffix.lower()
    mime = mime_types[normalized] if normalized in mime_types else "image/webp"
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


def _read_image_data_uri_sync(path: Path) -> str:
    if not path.is_file() or path.stat().st_size <= 0:
        return ""
    return image_data_uri(path.read_bytes(), path.suffix)


async def read_image_data_uri(path: Path | None) -> str:
    """在线程池读取图片文件并编码为 data URI；文件缺失或为空返回空串。"""
    if path is None:
        return ""
    return await to_thread(_read_image_data_uri_sync)(path)
