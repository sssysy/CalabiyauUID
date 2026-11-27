"""按 UID 或游戏昵称解析玩家 playerId（仅接受唯一精确匹配）。"""

from ..api.dakanu.client import DakanuError
from ..api.dakanu.requests import search_players
from ..api.dakanu.models.player import DakanuPlayerSuggestion


def is_numeric_uid(value: str) -> bool:
    """判断输入是否为纯 ASCII 数字 UID。"""
    return bool(value) and value.isascii() and value.isdigit()


def _format_candidate(item: DakanuPlayerSuggestion) -> str:
    if item.matchedBy == "previous-nickname" and item.matchedName != item.nickname:
        return f"- {item.nickname}（曾用名：{item.matchedName}，UID：{item.playerId}）"
    return f"- {item.nickname}（UID：{item.playerId}）"


def _format_candidates(suggestions: list[DakanuPlayerSuggestion], limit: int = 5) -> str:
    return "\n".join(_format_candidate(item) for item in suggestions[:limit])


def _dedupe_by_player_id(items: list[DakanuPlayerSuggestion]) -> list[DakanuPlayerSuggestion]:
    unique: dict[str, DakanuPlayerSuggestion] = {}
    for item in items:
        player_id = item.playerId
        if player_id not in unique:
            unique[player_id] = item
    return list(unique.values())


async def resolve_player_input(raw_query: str) -> str:
    """把 UID 或游戏昵称解析为唯一 playerId；无唯一精确匹配时抛出 DakanuError。"""
    cleaned = raw_query.strip()
    if not cleaned:
        raise DakanuError("请提供卡拉彼丘 UID 或游戏昵称。")
    if is_numeric_uid(cleaned):
        return cleaned

    suggestions = _dedupe_by_player_id(await search_players(cleaned))
    if not suggestions:
        raise DakanuError(f"没有找到昵称为「{cleaned}」的玩家，请确认完整昵称或改用 UID。")

    exact_matches = [item for item in suggestions if item.exact]
    if len(exact_matches) == 1:
        return exact_matches[0].playerId
    if len(exact_matches) > 1:
        candidates = _format_candidates(exact_matches)
        raise DakanuError(f"找到多个与「{cleaned}」精确匹配的玩家，请改用 UID：\n{candidates}")

    candidates = _format_candidates(suggestions)
    raise DakanuError(f"未找到昵称为「{cleaned}」的精确匹配，请确认完整昵称或改用 UID：\n{candidates}")
