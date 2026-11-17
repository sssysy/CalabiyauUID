"""卡拉彼丘战绩分析与复盘能力代理节点。"""

from gsuid_core.ai_core.agent_node import TASK_BASICS_PACK, AgentNode, register_agent_node

_ANALYST_PROMPT = """你是卡拉彼丘（Calabiyau）战绩与版本数据分析代理，只负责依据插件工具返回的真实数据完成复盘、对比与上分建议。

【工具优先级 · 硬门】
1. 查询玩家生涯数据或最近对局：优先调 `calabiyau_query_player_text`（纯文本快速取数）或 `calabiyau_stats_summary` / `calabiyau_recent_matches`。
2. 需要查看单场详细记分板与双方阵容：先从玩家战绩摘要提取 `roomId`，再调 `calabiyau_query_match_detail`。
3. 涉及版本角色强度、上分推荐、绝活榜或排位门槛：必须调用 `calabiyau_roles_ranking`、`calabiyau_ranking`、`calabiyau_role_board_ranking`。
4. 角色俗称/别名不确定时调 `calabiyau_lookup_role` 归一化；涉及战队/活动/活跃趋势调对应插件工具。
5. `web_search_tool` / `web_fetch_tool` 仅能补充官方公告背景，严禁用网页搜索结果替代任何玩家个人战绩、段位或实时榜单数字。
6. 未实际调用插件工具取得数据前，禁止给出具体数值分析或编造胜率、KD、段位与对局记录。

【数据边界与交付要求】
- 玩家战绩来源于本地快照：输出分析时必须核对并注明本地快照时间；若本地无缓存，明确提示需要先执行绑定或刷新，不擅自猜数。
- 排行榜的排名 `rankPos` 可能存在并列重复，按接口原值陈述，不要自行改写为连续名次。
- 输出结论需条理清晰、数据有据可查（列出关键样本场次、胜率、KD、场均伤害及对比结论）。"""


def register_calabiyau_analyst_node() -> None:
    """注册卡拉彼丘战绩分析能力代理节点。"""
    register_agent_node(
        AgentNode(
            node_id="calabiyau_analyst_agent",
            display_name="卡拉彼丘战绩分析代理",
            prompt=_ANALYST_PROMPT,
            when_to_use=(
                "卡拉彼丘（Calabiyau / 卡丘）玩家战绩深度复盘、单局记分板拆解、"
                "版本超弦体胜率与出场率对比、排位上分与选角建议、战队及排行榜综合分析。"
            ),
            match_keywords=[
                "卡拉彼丘",
                "卡丘",
                "klbq",
                "Calabiyau",
                "超弦体",
                "战绩分析",
                "复盘",
                "上分建议",
            ],
            tool_packs=[TASK_BASICS_PACK],
            tool_names=[
                "calabiyau_query_player_text",
                "calabiyau_query_match_detail",
                "calabiyau_lookup_role",
                "calabiyau_stats_summary",
                "calabiyau_recent_matches",
                "calabiyau_roles_ranking",
                "calabiyau_ranking",
                "calabiyau_role_board_ranking",
                "calabiyau_clan_info",
                "calabiyau_event_timeline",
            ],
            boundary_override="",
            source="plugin",
        )
    )


register_calabiyau_analyst_node()
