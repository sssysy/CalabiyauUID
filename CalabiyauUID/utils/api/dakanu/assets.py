"""Dakanu 站点静态图片 URL 构造。"""

from __future__ import annotations

from .client import BASE_URL

_ROLE_SLUGS: dict[int, str] = {
    101: "michele",
    105: "audrey",
    107: "maddelena",
    108: "nobunaga",
    109: "reiichi",
    110: "bai_mo",
    112: "fuchsia",
    115: "flavia",
    119: "eika",
    120: "fragrans",
    121: "yugiri",
    122: "mara",
    123: "leona",
    124: "kokona",
    125: "qian_dai",
    126: "nono",
    128: "lawine",
    130: "xi",
    131: "yvette",
    132: "ming",
    133: "meredith",
    137: "kanami",
    146: "celestia",
    205: "galatea",
}


def role_image_url(role_id: int) -> str:
    """按角色 ID 返回站点角色立绘地址；未知角色返回空串。"""
    slug = _ROLE_SLUGS.get(role_id)
    return f"{BASE_URL}/roles/{slug}.webp" if slug else ""


def avatar_image_url(avatar_id: int) -> str:
    """按头像 ID 返回站点头像地址。"""
    return f"{BASE_URL}/avatars/{avatar_id}.webp"


def tier_image_url(tier_index: int) -> str:
    """按段位图标编号返回站点段位图标地址。"""
    return f"{BASE_URL}/tiers/tier-{tier_index}.png" if tier_index > 0 else ""


def challenge_tier_image_url(tier_index: int) -> str:
    """按挑战赛段位编号返回站点图标地址。"""
    return f"{BASE_URL}/challenge-rank/tier-{tier_index}.png" if 1 <= tier_index <= 9 else ""


def chat_emote_image_url(emote_id: str) -> str:
    """按聊天表情 ID 返回站点表情地址。"""
    cleaned = emote_id.strip().lstrip("#")
    return f"{BASE_URL}/chat-emotes/{cleaned}.webp" if cleaned.isascii() and cleaned.isdigit() else ""


def medal_image_url(medal_id: int) -> str:
    """按勋章 ID 返回站点勋章地址；非法 ID 返回空串。"""
    return f"{BASE_URL}/medals/{medal_id}.webp" if medal_id > 0 else ""
