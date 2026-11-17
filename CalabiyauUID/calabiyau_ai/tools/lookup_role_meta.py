"""卡拉彼丘超弦体正式名、别名、阵营与定位反查工具。"""

from gsuid_core.ai_core.register import ai_tools

from ...utils.helper.maps import ROLE_NAMES, resolve_role_meta, resolve_role_alias


@ai_tools(
    category="default",
    capability_domain="卡拉彼丘资料",
    context_tags=["卡拉彼丘", "游戏"],
    covers=["卡拉彼丘超弦体角色ID、正式名称、玩家外号别名、所属阵营与定位查询"],
    aliases=["卡拉彼丘·查角色资料", "卡拉彼丘·角色别名反查"],
    timeout=15.0,
)
async def calabiyau_lookup_role(query: str) -> str:
    """
    根据超弦体角色名、常用外号/黑话、拼音首字母或角色 ID 查询标准资料。
    支持例如 "糖猫"、"小画家"、"牢大"、"xh"、"146" 等输入。

    Args:
        query: 角色正式名、别名、拼音或数字角色 ID
    """
    cleaned = query.strip()
    if not cleaned:
        all_names = "、".join(ROLE_NAMES[rid][0] for rid in sorted(ROLE_NAMES) if ROLE_NAMES[rid])
        return f"请提供要查询的超弦体名称或别名。当前已收录：{all_names}"

    role_id: int | None = None
    if cleaned.isascii() and cleaned.isdigit():
        candidate_id = int(cleaned)
        if candidate_id in ROLE_NAMES:
            role_id = candidate_id
    else:
        role_id = resolve_role_alias(cleaned)

    if role_id is None or role_id not in ROLE_NAMES or not ROLE_NAMES[role_id]:
        return f"未找到与「{cleaned}」匹配的卡拉彼丘超弦体。"

    names = ROLE_NAMES[role_id]
    formal_name = names[0]
    aliases = "、".join(names[1:]) if len(names) > 1 else "无"
    meta = resolve_role_meta(role_id)
    if meta is None:
        return f"超弦体：{formal_name}（ID：{role_id}）｜别名：{aliases}"
    return (
        f"超弦体：{formal_name}（ID：{role_id}）\n"
        f"阵营：{meta.faction_name} | 定位：{meta.position_name}\n"
        f"常见别名：{aliases}"
    )
