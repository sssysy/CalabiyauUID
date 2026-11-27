"""战队信息 HTML 卡片。"""

from dataclasses import dataclass
from collections.abc import Mapping, Sequence

from ..render import CARD_WIDTH, CardTemplateContext, render_card
from ....api.dakanu.models.clan import DakanuClan, DakanuClanMember


@dataclass(frozen=True)
class ClanMemberItem:
    rank_text: str
    avatar: str
    initial: str
    nickname: str
    is_leader: bool
    position_text: str
    sub_text: str


@dataclass(frozen=True)
class ClanMemberPair:
    left: ClanMemberItem
    right: ClanMemberItem | None


@dataclass(frozen=True)
class ClanTemplateContext(CardTemplateContext):
    clan_name: str = ""
    clan_level_text: str = ""
    clan_id: str = ""
    intro: str = ""
    avg_level_text: str = "—"
    max_level_text: str = "—"
    rows: tuple[ClanMemberPair, ...] = ()


def _is_leader_member(member: DakanuClanMember) -> bool:
    return bool(member.isLeader) or member.position == 1


def _sort_members(members: Sequence[DakanuClanMember]) -> list[DakanuClanMember]:
    return sorted(
        members,
        key=lambda item: (
            0 if _is_leader_member(item) else 1,
            -(item.level if item.level is not None else -1),
        ),
    )


def _build_member_item(
    index: int,
    member: DakanuClanMember,
    avatar_images: Mapping[int, str],
) -> ClanMemberItem:
    player_id = member.playerId
    nickname = member.nickname.strip() or f"玩家 {player_id}"
    avatar_id = member.avatarId
    avatar = avatar_images[avatar_id] if avatar_id is not None and avatar_id in avatar_images else ""
    is_leader = _is_leader_member(member)
    position = member.position
    position_text = f"职位 {position}" if not is_leader and position is not None else ""
    level = member.level
    sub_parts: list[str] = []
    if level is not None:
        sub_parts.append(f"Lv.{level}")
    sub_parts.append(f"UID {player_id}")
    return ClanMemberItem(
        rank_text=f"{index:02d}",
        avatar=avatar,
        initial=nickname[:1] or "?",
        nickname=nickname,
        is_leader=is_leader,
        position_text=position_text,
        sub_text=" · ".join(sub_parts),
    )


def build_clan_context(
    clan: DakanuClan,
    members: Sequence[DakanuClanMember],
    avatar_images: Mapping[int, str],
) -> ClanTemplateContext:
    """构造战队信息卡片渲染上下文。"""
    ordered = _sort_members(members)
    items = tuple(_build_member_item(idx + 1, member, avatar_images) for idx, member in enumerate(ordered))
    rows: list[ClanMemberPair] = []
    for idx in range(0, len(items), 2):
        left = items[idx]
        right = items[idx + 1] if idx + 1 < len(items) else None
        rows.append(ClanMemberPair(left=left, right=right))

    levels = [member.level for member in ordered if member.level is not None]
    avg_level_text = f"Lv.{round(sum(levels) / len(levels))}" if levels else "—"
    max_level_text = f"Lv.{max(levels)}" if levels else "—"

    return ClanTemplateContext(
        clan_name=clan.name.strip() or "未命名战队",
        clan_level_text=f"Lv.{clan.level}",
        clan_id=clan.clanId,
        intro=clan.intro.strip(),
        avg_level_text=avg_level_text,
        max_level_text=max_level_text,
        rows=tuple(rows),
    )


async def render_clan_card(
    clan: DakanuClan,
    members: Sequence[DakanuClanMember],
    avatar_images: Mapping[int, str],
) -> bytes:
    """渲染战队信息 PNG 图片字节。"""
    context = build_clan_context(clan, members, avatar_images)
    return await render_card("clan_card.html", context, width=CARD_WIDTH)
