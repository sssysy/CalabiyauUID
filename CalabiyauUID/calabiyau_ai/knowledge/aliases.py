"""卡拉彼丘角色与模式专有名词别名注册。"""

from gsuid_core.ai_core.register import ai_alias

from ...utils.helper.maps import ROLE_NAMES

_CALABIYAU_SCOPE = "CalabiyauUID"

_DOMAIN_ALIASES: dict[str, list[str]] = {
    "卡拉彼丘": ["卡丘", "Calabiyau", "klbq", "kq", "弦能"],
    "晶源感染": ["生化", "生化模式", "感染", "感染模式"],
    "极限推进": ["推车", "推车模式"],
    "团队乱斗": ["团竞", "团队竞技", "乱斗"],
    "爆破模式": ["排位", "排位赛", "爆破"],
}


def register_calabiyau_aliases() -> None:
    """注册超弦体常用俗称与游戏模式别名，隔离作用域避免跨游戏串味。"""
    for names in ROLE_NAMES.values():
        if len(names) <= 1:
            continue
        formal_name = names[0].strip()
        alias_list = [item.strip() for item in names[1:] if item.strip()]
        if formal_name and alias_list:
            ai_alias(formal_name, alias_list, scope=_CALABIYAU_SCOPE)

    for formal_name, alias_list in _DOMAIN_ALIASES.items():
        ai_alias(formal_name, alias_list, scope=_CALABIYAU_SCOPE)


register_calabiyau_aliases()
