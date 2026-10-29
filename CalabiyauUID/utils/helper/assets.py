"""插件数据仓库中的本地素材路径。"""

from pathlib import Path

from ..utils.paths import DATA_DIR

ASSET_DIR: Path = DATA_DIR / "assets"

_IMAGE_SUFFIXES = (".webp", ".png", ".jpg", ".jpeg", ".gif")


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
