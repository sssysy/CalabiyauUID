"""世界频道动态 HTML 卡片。"""

import re
from datetime import datetime
from dataclasses import dataclass
from collections.abc import Mapping, Sequence

from .render import CardTemplateContext, render_card, render_template
from ...api.dakanu import DakanuChatMessage, DakanuChatAggregate
from .summary_card import tier_display

DEFAULT_WORLD_CHAT_LIMIT = 25

_EMOTE_RE = re.compile(
    r'\[style=(?:"Image"|\'Image\')\s+id=(?:"#?(\d+)"|\'#?(\d+)\')\]',
    re.IGNORECASE,
)
_KV_RE = re.compile(r"(?:^|,)([A-Za-z][A-Za-z0-9_]*)=([\s\S]*?)(?=,[A-Za-z][A-Za-z0-9_]*=|$)")
_MEMBER_RE = re.compile(r"(\d+)\s*/\s*(\d+)")


@dataclass(frozen=True)
class WorldChatAssets:
    avatar_images: Mapping[int, str]
    role_images: Mapping[int, str]
    emote_images: Mapping[str, str]
    role_names: Mapping[int, str]


@dataclass(frozen=True)
class ChatTextPart:
    kind: str  # "text" | "emote" | "emote_fallback"
    text: str = ""
    uri: str = ""


@dataclass(frozen=True)
class MetricCellItem:
    label: str
    value: str


@dataclass(frozen=True)
class RoleChipItem:
    uri: str
    label: str


@dataclass(frozen=True)
class SeatBarItem:
    filled: bool


@dataclass(frozen=True)
class PlayerCardInfo:
    title: str
    level: int | None
    tags: tuple[str, ...]
    metrics: tuple[MetricCellItem, ...]
    roles: tuple[RoleChipItem, ...]


@dataclass(frozen=True)
class TeamCardInfo:
    title: str
    mode_label: str
    score_limit: str
    status_label: str
    is_closed: bool
    has_seats: bool
    seats_text: str
    seats: tuple[SeatBarItem, ...]


@dataclass(frozen=True)
class ClanCardInfo:
    clan_name: str
    clan_id: str


@dataclass(frozen=True)
class WorldChatRowItem:
    avatar_uri: str
    initial: str
    nickname: str
    level_text: str
    player_id: str
    sent_time: str
    card_kind: str  # "text" | "player" | "team" | "clan"
    text_parts: tuple[ChatTextPart, ...] = ()
    player_card: PlayerCardInfo | None = None
    team_card: TeamCardInfo | None = None
    clan_card: ClanCardInfo | None = None


@dataclass(frozen=True)
class WorldChatTemplateContext(CardTemplateContext):
    population_text: str = "—"
    rows: tuple[WorldChatRowItem, ...] = ()


def _clean_val(val: str | None) -> str | None:
    if val is None:
        return None
    cleaned = val.strip()
    if not cleaned or cleaned.lower() in {"nil", "null", "none", "undefined"}:
        return None
    return cleaned


def _to_int(val: str | None) -> int | None:
    cleaned = _clean_val(val)
    if cleaned is None:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def _kv_value(kv: Mapping[str, str], key: str) -> str | None:
    return kv[key] if key in kv else None


def _parse_kv_message(raw_message: str) -> dict[str, str] | None:
    stripped = raw_message.strip()
    if not stripped.startswith("type="):
        return None
    kv: dict[str, str] = {}
    for match in _KV_RE.finditer(stripped):
        kv[match.group(1)] = match.group(2).strip()
    return kv


def _extract_player_card_role_ids(kv: Mapping[str, str]) -> list[int]:
    roles: list[int] = []
    for key in ("role1", "role2", "role3"):
        role_id = _to_int(_kv_value(kv, key))
        if role_id is not None and role_id > 0 and role_id not in roles:
            roles.append(role_id)
    return roles


def select_recent_messages(
    messages: Sequence[DakanuChatMessage],
    *,
    limit: int = DEFAULT_WORLD_CHAT_LIMIT,
) -> list[DakanuChatMessage]:
    """按玩家、时间与正文去重后升序截取最新 N 条消息。"""
    seen: dict[tuple[str, int, str], DakanuChatMessage] = {}
    for msg in messages:
        key = (msg["player_id"], msg["sent_at"], msg["message"])
        if key not in seen:
            seen[key] = msg
    ordered = sorted(seen.values(), key=lambda item: (item["sent_at"], item["player_id"]))
    if limit <= 0:
        return []
    return ordered[-limit:]


def collect_chat_asset_ids(
    messages: Sequence[DakanuChatMessage],
) -> tuple[set[int], set[int], set[str]]:
    """收集消息列表中所需的头像 ID、名片角色 ID 与聊天表情 ID。"""
    avatar_ids: set[int] = set()
    role_ids: set[int] = set()
    emote_ids: set[str] = set()

    for msg in messages:
        icon_id = msg["icon"]
        if icon_id is not None and icon_id > 0:
            avatar_ids.add(icon_id)
        raw_msg = msg["message"]
        kv = _parse_kv_message(raw_msg)
        if kv is not None and _to_int(_kv_value(kv, "type")) == 1:
            role_ids.update(_extract_player_card_role_ids(kv))
            continue
        for match in _EMOTE_RE.finditer(raw_msg):
            emote_id = match.group(1) or match.group(2) or ""
            if emote_id:
                emote_ids.add(emote_id)

    return avatar_ids, role_ids, emote_ids


def _parse_text_parts(
    raw_message: str,
    emote_images: Mapping[str, str],
) -> tuple[ChatTextPart, ...]:
    parts: list[ChatTextPart] = []
    pos = 0
    for match in _EMOTE_RE.finditer(raw_message):
        if match.start() > pos:
            parts.append(ChatTextPart(kind="text", text=raw_message[pos : match.start()]))
        emote_id = match.group(1) or match.group(2) or ""
        uri = emote_images[emote_id] if emote_id in emote_images else ""
        if uri:
            parts.append(ChatTextPart(kind="emote", uri=uri))
        else:
            parts.append(ChatTextPart(kind="emote_fallback", text=f"[表情 {emote_id}]"))
        pos = match.end()
    if pos < len(raw_message):
        parts.append(ChatTextPart(kind="text", text=raw_message[pos:]))
    if not parts:
        return (ChatTextPart(kind="text", text=raw_message),)
    return tuple(parts)


def _build_player_card(kv: Mapping[str, str], assets: WorldChatAssets) -> PlayerCardInfo:
    seg = _to_int(_kv_value(kv, "rank"))
    pos = _to_int(_kv_value(kv, "rankPos"))
    wins = _to_int(_kv_value(kv, "winCount"))

    tags: list[str] = []
    if seg is not None:
        seg_label, _, tier_idx = tier_display(seg)
        if tier_idx > 0:
            tags.append(seg_label)
    if pos is not None and pos > 0:
        tags.append(f"#{pos}")
    date_str = _clean_val(_kv_value(kv, "time"))
    if date_str is not None:
        tags.append(date_str)

    metrics: list[MetricCellItem] = []
    if wins is not None:
        metrics.append(MetricCellItem(label="胜场", value=str(wins)))
    for key in ("battleData1", "battleData2", "battleData3"):
        raw_val = _clean_val(_kv_value(kv, key))
        if raw_val is None:
            continue
        if ":" in raw_val or "：" in raw_val:
            colon_idx = raw_val.find(":") if ":" in raw_val else raw_val.find("：")
            metrics.append(
                MetricCellItem(
                    label=raw_val[:colon_idx].strip(),
                    value=raw_val[colon_idx + 1 :].strip(),
                )
            )
        else:
            metrics.append(MetricCellItem(label="数据", value=raw_val))

    role_chips: list[RoleChipItem] = []
    for role_id in _extract_player_card_role_ids(kv):
        uri = assets.role_images[role_id] if role_id in assets.role_images else ""
        name = assets.role_names[role_id] if role_id in assets.role_names else f"角色 {role_id}"
        role_chips.append(RoleChipItem(uri=uri, label=name))

    return PlayerCardInfo(
        title=_clean_val(_kv_value(kv, "title")) or "玩家名片",
        level=_to_int(_kv_value(kv, "level")),
        tags=tuple(tags),
        metrics=tuple(metrics),
        roles=tuple(role_chips),
    )


def _build_team_card(kv: Mapping[str, str]) -> TeamCardInfo:
    member_text = _clean_val(_kv_value(kv, "memberNum")) or ""
    match = _MEMBER_RE.search(member_text)
    cur_members = int(match.group(1)) if match is not None else None
    max_members = int(match.group(2)) if match is not None else None

    mode_type = _to_int(_kv_value(kv, "modeType"))
    if mode_type == 2:
        mode_label = "排位组队"
    elif mode_type == 1:
        mode_label = "常规组队"
    else:
        mode_label = "组队招募"

    status_val = _clean_val(_kv_value(kv, "status"))
    if status_val == "1":
        status_label = "招募中"
    elif status_val == "0":
        status_label = "已结束"
    else:
        status_label = ""

    seats: list[SeatBarItem] = []
    seats_text = ""
    if cur_members is not None:
        max_n = min(10, max(1, max_members or 5))
        seats = [SeatBarItem(filled=idx <= cur_members) for idx in range(1, max_n + 1)]
        seats_text = f"{cur_members} / {max_members or '?'}"

    return TeamCardInfo(
        title=_clean_val(_kv_value(kv, "title")) or "队伍招募",
        mode_label=mode_label,
        score_limit=_clean_val(_kv_value(kv, "scoreLimit")) or "",
        status_label=status_label,
        is_closed=status_label == "已结束",
        has_seats=cur_members is not None,
        seats_text=seats_text,
        seats=tuple(seats),
    )


def _build_clan_card(kv: Mapping[str, str]) -> ClanCardInfo:
    clan_name = _clean_val(_kv_value(kv, "clanName")) or _clean_val(_kv_value(kv, "ClanName")) or "未命名战队"
    clan_id = _clean_val(_kv_value(kv, "clanId")) or _clean_val(_kv_value(kv, "ClanId")) or ""
    return ClanCardInfo(clan_name=clan_name, clan_id=clan_id)


def build_world_chat_context(
    aggregate: DakanuChatAggregate,
    assets: WorldChatAssets,
    *,
    limit: int = DEFAULT_WORLD_CHAT_LIMIT,
) -> WorldChatTemplateContext:
    """把 Dakanu 世界频道聚合响应整理为模板上下文。"""
    population = aggregate["selection"]["population"]
    population_text = str(population) if population is not None else "—"
    recent_msgs = select_recent_messages(aggregate["messages"], limit=limit)

    rows: list[WorldChatRowItem] = []
    for msg in recent_msgs:
        player_id = msg["player_id"]
        nickname = msg["nick"] or player_id or "未知玩家"
        icon_id = msg["icon"]
        avatar_uri = assets.avatar_images[icon_id] if icon_id is not None and icon_id in assets.avatar_images else ""
        initial = nickname[:1].upper() if nickname else "?"
        sent_time = datetime.fromtimestamp(msg["sent_at"]).strftime("%H:%M")

        raw_msg = msg["message"]
        kv = _parse_kv_message(raw_msg)
        card_type = _to_int(_kv_value(kv, "type")) if kv is not None else None
        level_val = msg["level"]

        if kv is not None and card_type == 1:
            player_card = _build_player_card(kv, assets)
            if level_val is None:
                level_val = player_card.level
            rows.append(
                WorldChatRowItem(
                    avatar_uri=avatar_uri,
                    initial=initial,
                    nickname=nickname,
                    level_text=f"Lv.{level_val}" if level_val is not None else "",
                    player_id=player_id,
                    sent_time=sent_time,
                    card_kind="player",
                    player_card=player_card,
                )
            )
        elif kv is not None and card_type == 2:
            rows.append(
                WorldChatRowItem(
                    avatar_uri=avatar_uri,
                    initial=initial,
                    nickname=nickname,
                    level_text=f"Lv.{level_val}" if level_val is not None else "",
                    player_id=player_id,
                    sent_time=sent_time,
                    card_kind="team",
                    team_card=_build_team_card(kv),
                )
            )
        elif kv is not None and card_type == 4:
            rows.append(
                WorldChatRowItem(
                    avatar_uri=avatar_uri,
                    initial=initial,
                    nickname=nickname,
                    level_text=f"Lv.{level_val}" if level_val is not None else "",
                    player_id=player_id,
                    sent_time=sent_time,
                    card_kind="clan",
                    clan_card=_build_clan_card(kv),
                )
            )
        else:
            rows.append(
                WorldChatRowItem(
                    avatar_uri=avatar_uri,
                    initial=initial,
                    nickname=nickname,
                    level_text=f"Lv.{level_val}" if level_val is not None else "",
                    player_id=player_id,
                    sent_time=sent_time,
                    card_kind="text",
                    text_parts=_parse_text_parts(raw_msg, assets.emote_images),
                )
            )

    return WorldChatTemplateContext(
        population_text=population_text,
        rows=tuple(rows),
    )


def render_world_chat_html(
    aggregate: DakanuChatAggregate,
    assets: WorldChatAssets,
    *,
    limit: int = DEFAULT_WORLD_CHAT_LIMIT,
) -> str:
    """渲染世界频道动态 HTML 字符串。"""
    context = build_world_chat_context(aggregate, assets, limit=limit)
    return render_template("world_chat_card.html", context)


async def render_world_chat_card(
    aggregate: DakanuChatAggregate,
    assets: WorldChatAssets,
    *,
    limit: int = DEFAULT_WORLD_CHAT_LIMIT,
) -> bytes:
    """把世界频道动态渲染为 PNG 图片字节。"""
    context = build_world_chat_context(aggregate, assets, limit=limit)
    return await render_card("world_chat_card.html", context)
