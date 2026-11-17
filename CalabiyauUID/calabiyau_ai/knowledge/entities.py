"""卡拉彼丘插件功能说明与基础设定知识库注册。"""

from gsuid_core.ai_core.models import KnowledgePoint
from gsuid_core.ai_core.register import ai_entity

from ...utils.helper.maps import ROLE_NAMES, resolve_role_meta

_PLUGIN_NAME = "CalabiyauUID"


def _build_roles_overview_content() -> str:
    lines: list[str] = ["# 卡拉彼丘超弦体图鉴与阵营定位", ""]
    for role_id in sorted(ROLE_NAMES):
        names = ROLE_NAMES[role_id]
        if not names:
            continue
        formal_name = names[0]
        aliases = "、".join(names[1:]) if len(names) > 1 else "无"
        meta = resolve_role_meta(role_id)
        meta_text = f"{meta.faction_name} · {meta.position_name}" if meta is not None else "未知阵营/定位"
        lines.append(f"- **{formal_name}**（ID：{role_id}，{meta_text}）｜常见别名：{aliases}")
    return "\n".join(lines)


def register_calabiyau_entities() -> None:
    """注册插件命令指南、玩法模式段位及超弦体知识条目。"""
    ai_entity(
        KnowledgePoint(
            id="calabiyau_commands_guide",
            plugin=_PLUGIN_NAME,
            title="CalabiyauUID 卡拉彼丘插件使用指南",
            content=(
                "# CalabiyauUID 使用指南\n\n"
                "所有用户命令均以固定前缀 `kq` 开头（当前仅支持国服数据）：\n"
                "- `kq绑定 <UID或昵称>`：绑定国服账号并拉取首次战绩快照\n"
                "- `kq解绑 <UID或昵称>`：解绑指定已绑定账号\n"
                "- `kq查看`：查看当前已绑定账号列表与主账号\n"
                "- `kq切换 [UID或昵称]`：切换当前主账号，留空切至下一个\n"
                "- `kq战绩总览 [UID或昵称]`：查看本地快照的生涯战绩总览卡片\n"
                "- `kq历史战绩`：查看当前绑定账号最近 8 场对局卡片\n"
                "- `kq刷新数据 [UID或昵称]`：强制刷新玩家战绩快照\n"
                "- `kq回放下载 <对局roomId>`：下载指定对局录像文件\n"
                "- `kq战队查询 [战队名或ID]`：查询指定或当前账号所在战队\n"
                "- `kq排位排行` / `kq团队排行` / `kq推进排行` / `kq挑战排行` / `kq感染排行`：各类模式排行榜\n"
                "- `kq超弦体排行 <角色名或ID>`：查看指定角色玩家榜单\n"
                "- `kq角色[排位|全部][出场率|胜率]排行`：查看全角色胜率与出场率统计\n"
                "- `kq活动` / `kq活跃图[周期]` / `kq世界聊天` / `kq封神榜 [UID或昵称]`：社区与活动查询\n"
                "- `kq订阅活动结束提醒` / `kq取消订阅活动结束提醒`：管理员订阅活动结束前 24 小时通知"
            ),
            tags=["CalabiyauUID", "卡拉彼丘", "帮助", "命令", "kq"],
        )
    )

    ai_entity(
        KnowledgePoint(
            id="calabiyau_modes_and_tiers",
            plugin=_PLUGIN_NAME,
            title="卡拉彼丘游戏模式与段位体系",
            content=(
                "# 游戏模式\n"
                "- 爆破模式（排位赛核心模式）\n"
                "- 团队乱斗（团竞模式）\n"
                "- 极限推进（推车模式）\n"
                "- 晶源感染（生化模式）\n"
                "- 挑战模式（休闲娱乐段位体系）\n\n"
                "# 排位段位梯度（从低到高）\n"
                "至纯物质（III~I）→ 升格分子（III~I）→ 虚空原子（IV~I）→ "
                "聚变质子（IV~I）→ 自由中子（IV~I）→ 束缚电子（V~I）→ "
                "禁闭夸克（V~I）→ 无限超弦 → 奇点\n\n"
                "# 挑战赛段位梯度（从低到高）\n"
                "青铜（V~I）→ 白银（V~I）→ 黄金（V~I）→ 铂金（V~I）→ "
                "翡翠（V~I）→ 钻石（V~I）→ 大师（V~I）→ 传奇（V~I）→ 王者"
            ),
            tags=["卡拉彼丘", "模式", "段位", "排位", "挑战赛"],
        )
    )

    ai_entity(
        KnowledgePoint(
            id="calabiyau_roles_overview",
            plugin=_PLUGIN_NAME,
            title="卡拉彼丘超弦体阵营定位总表",
            content=_build_roles_overview_content(),
            tags=["卡拉彼丘", "超弦体", "角色", "阵营", "定位"],
        )
    )

    for role_id in sorted(ROLE_NAMES):
        names = ROLE_NAMES[role_id]
        if not names:
            continue
        formal_name = names[0]
        aliases = [item for item in names[1:] if item]
        meta = resolve_role_meta(role_id)
        faction = meta.faction_name if meta is not None else "未知"
        position = meta.position_name if meta is not None else "未知"
        alias_line = "、".join(aliases) if aliases else "暂无"
        ai_entity(
            KnowledgePoint(
                id=f"calabiyau_role_{role_id}",
                plugin=_PLUGIN_NAME,
                title=f"{formal_name} - 卡拉彼丘超弦体基础资料",
                entity=formal_name,
                content=(
                    f"# {formal_name}\n\n"
                    f"- 角色 ID：{role_id}\n"
                    f"- 所属阵营：{faction}\n"
                    f"- 团队定位：{position}\n"
                    f"- 玩家常用别名：{alias_line}\n"
                    f"- 可配合 `kq超弦体排行 {formal_name}` 或角色胜率榜查询当前强度表现。"
                ),
                tags=["卡拉彼丘", "超弦体", formal_name, faction, position, *aliases],
            )
        )


register_calabiyau_entities()
