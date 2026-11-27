"""卡拉彼丘插件功能说明、设定图鉴与 Wiki 知识库注册。"""

from pathlib import Path

from pydantic import Field, BaseModel, ConfigDict

from gsuid_core.logger import logger
from gsuid_core.ai_core.models import KnowledgePoint
from gsuid_core.ai_core.register import ai_entity, unregister_entities_of_plugin
from gsuid_core.ai_core.configs.ai_config import ai_config

from ...utils.helper.maps import ROLE_NAMES
from ...utils.utils.paths import RESOURCE_DIR

_PLUGIN_NAME = "CalabiyauUID"
_LOG_TAG = "[卡拉彼丘·知识库]"


class _KnowledgeModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore", frozen=True)


class _SkillModeValue(_KnowledgeModel):
    mode: str
    values: dict[str, str]


class _RoleSkill(_KnowledgeModel):
    slot: str
    key: str
    name: str
    description: str
    analysis: str
    mode_values: tuple[_SkillModeValue, ...]


class _UnlockNodes(_KnowledgeModel):
    weapon: int
    defense: int
    skill: int


class _RoleAwakening(_KnowledgeModel):
    tier: int
    name: str
    description: str
    unlock_nodes: _UnlockNodes


class _GrowthNode(_KnowledgeModel):
    desc: str
    cost: int
    effect: str


class _GrowthGroup(_KnowledgeModel):
    slot: str
    name: str
    nodes: tuple[_GrowthNode, ...]


class _GrowthMode(_KnowledgeModel):
    mode: str
    groups: tuple[_GrowthGroup, ...]


class _RoleData(_KnowledgeModel):
    role_id: int = Field(alias="id")
    name: str
    profile: dict[str, str]
    available_weapons: tuple[str, ...]
    base_stats_pc: dict[str, str]
    skills: tuple[_RoleSkill, ...]
    awakenings: tuple[_RoleAwakening, ...]
    growth_network: tuple[_GrowthMode, ...]


class _PrimaryWeaponData(_KnowledgeModel):
    name: str
    weapon_type: str
    users: tuple[str, ...]
    intro: str
    stats_pc: dict[str, str]
    damage_falloff_pc: dict[str, str]
    extra_notes: tuple[str, ...]
    growth_network: tuple[_GrowthMode, ...]
    detail_stats: dict[str, str]


class _SecondaryWeaponData(_KnowledgeModel):
    name: str
    obtain: str
    intro: str
    stats_pc: dict[str, str]
    damage_falloff_pc: dict[str, str]


class _MeleeWeaponData(_KnowledgeModel):
    name: str
    obtain: str
    intro: str
    damage_pc: dict[str, str]
    handling: tuple[str, ...]


class _TacticalItemData(_KnowledgeModel):
    name: str
    obtain: str
    intro: str
    effect: str
    extra_data: tuple[str, ...]
    cooldowns_sec: dict[str, int]


class _KristallData(_KnowledgeModel):
    kristall_id: int = Field(alias="id")
    name: str
    profile: dict[str, str]
    stats: dict[str, str]
    skills: dict[str, str]


class _ManifestEntry(_KnowledgeModel):
    path: str


class _WeaponsManifest(_KnowledgeModel):
    primary: tuple[_ManifestEntry, ...]
    secondary: tuple[_ManifestEntry, ...]
    melee: tuple[_ManifestEntry, ...]
    tactical: tuple[_ManifestEntry, ...]


class _KnowledgeManifest(_KnowledgeModel):
    roles: tuple[_ManifestEntry, ...]
    weapons: _WeaponsManifest
    kristall: tuple[_ManifestEntry, ...]


class _BaseSpeedRow(_KnowledgeModel):
    state: str
    sprint: str
    walk_hipfire: str
    ads: str


class _PrimarySpeedRow(_BaseSpeedRow):
    weapon_type: str
    roles: str


class _SpeedTable(_KnowledgeModel):
    unarmed_or_secondary_or_tactical: tuple[_BaseSpeedRow, ...]
    holding_primary_weapon: tuple[_PrimarySpeedRow, ...]


class _KnowledgeIndex(_KnowledgeModel):
    manifest: _KnowledgeManifest
    speed_table: _SpeedTable
    tactical_cooldowns: dict[str, dict[str, int]]


def _load_model[ModelT: BaseModel](path: Path, model_cls: type[ModelT]) -> ModelT:
    return model_cls.model_validate_json(path.read_text(encoding="utf-8"))


def _resolve_safe_path(base_dir: Path, rel_path: str) -> Path:
    resolved = (base_dir / rel_path).resolve()
    if base_dir.resolve() not in resolved.parents:
        raise ValueError(f"非法的知识库相对路径：{rel_path}")
    return resolved


def _format_kv_bullets(mapping: dict[str, str]) -> list[str]:
    return [f"- {key}：{val}" for key, val in mapping.items() if val]


def _format_growth_lines(modes: tuple[_GrowthMode, ...]) -> list[str]:
    lines: list[str] = []
    for mode in modes:
        lines.append(f"### {mode.mode}")
        for group in mode.groups:
            header = f"- **{group.slot}**（{group.name}）：" if group.name != group.slot else f"- **{group.slot}**："
            lines.append(header)
            for node in group.nodes:
                cost_text = f"{node.cost} 能量点" if node.cost > 0 else "能量点见局内"
                effect_text = "；".join(node.effect.splitlines()) if node.effect else "无额外数值变更说明"
                desc_text = f"{node.desc} | " if node.desc else ""
                lines.append(f"  - [{cost_text}] {desc_text}{effect_text}")
    return lines


def _register_core_guides() -> int:
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
                "- `kq兑换码`：查看当前未失效的兑换码及奖励内容\n"
                "- `kq订阅兑换码` / `kq取消订阅兑换码`：订阅新兑换码上线与临期 24 小时通知\n"
                "- `kq订阅活动结束提醒` / `kq取消订阅活动结束提醒`：订阅活动结束前 24 小时通知"
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
    return 2


def _register_role_entities(role: _RoleData) -> int:
    aliases = [item for item in ROLE_NAMES[role.role_id][1:] if item] if role.role_id in ROLE_NAMES else []
    faction = role.profile["阵营"] if "阵营" in role.profile else "未知"
    position = role.profile["定位"] if "定位" in role.profile else "未知"
    primary_weapon = role.profile["武器名称"] if "武器名称" in role.profile else ""
    weapon_type = role.profile["武器类型"] if "武器类型" in role.profile else ""

    profile_lines: list[str] = [
        f"# {role.name} - 超弦体档案（PC端）",
        "",
        f"- 角色 ID：{role.role_id}",
        f"- 所属阵营：{faction}",
        f"- 团队定位：{position}",
        f"- 玩家常用别名：{'、'.join(aliases) if aliases else '暂无'}",
        f"- 可用主武器：{'、'.join(role.available_weapons) if role.available_weapons else '暂无'}",
    ]
    if role.base_stats_pc:
        stats_joined = " / ".join(f"{k} {v}" for k, v in role.base_stats_pc.items() if v)
        profile_lines.append(f"- 基础属性（PC）：{stats_joined}")
    profile_lines.extend(_format_kv_bullets(role.profile))
    profile_lines.append(f"- 战绩指令：可使用 `kq超弦体排行 {role.name}` 查询当前版本玩家榜。")

    tags_common = [
        "卡拉彼丘",
        "超弦体",
        role.name,
        faction,
        position,
        *[w for w in role.available_weapons if w],
        *aliases,
    ]
    if weapon_type:
        tags_common.append(weapon_type)

    ai_entity(
        KnowledgePoint(
            id=f"calabiyau_role_{role.role_id}_profile",
            plugin=_PLUGIN_NAME,
            title=f"{role.name} - 卡拉彼丘超弦体档案与属性",
            entity=role.name,
            content="\n".join(profile_lines),
            tags=[*tags_common, "档案", "背景", "武器"],
        )
    )

    skill_lines: list[str] = [f"# {role.name} - 技能、觉醒与弦能增幅网络（PC端）", ""]
    skill_lines.append("## 角色技能")
    for skill in role.skills:
        skill_lines.append(f"### {skill.slot}（{skill.key}）｜{skill.name}")
        if skill.description:
            skill_lines.append(f"- 官方描述：{skill.description}")
        if skill.analysis:
            skill_lines.append(f"- 机制解析：\n{skill.analysis}")
        if skill.mode_values:
            skill_lines.append("- 各模式数值：")
            for mv in skill.mode_values:
                kv_text = "；".join(f"{k}={v}" for k, v in mv.values.items())
                skill_lines.append(f"  - [{mv.mode}] {kv_text}")
        skill_lines.append("")

    if role.awakenings:
        skill_lines.append("## 技能觉醒")
        for awk in role.awakenings:
            skill_lines.append(
                f"- **觉醒 {awk.tier}：{awk.name}**"
                f"（需武器 {awk.unlock_nodes.weapon} / 防御 {awk.unlock_nodes.defense} / 技能 {awk.unlock_nodes.skill} 节点）："
                f"{awk.description}"
            )
        skill_lines.append("")

    if role.growth_network:
        skill_lines.append("## 弦能增幅网络")
        skill_lines.extend(_format_growth_lines(role.growth_network))

    ai_entity(
        KnowledgePoint(
            id=f"calabiyau_role_{role.role_id}_skills",
            plugin=_PLUGIN_NAME,
            title=f"{role.name} - 技能机制、觉醒与弦能增幅网络",
            entity=role.name,
            content="\n".join(skill_lines),
            tags=[*tags_common, "技能", "觉醒", "弦能增幅网络", primary_weapon],
        )
    )
    return 2


def _register_primary_weapon_entity(weapon: _PrimaryWeaponData) -> None:
    lines: list[str] = [
        f"# {weapon.name} - 主武器资料（PC端）",
        "",
        f"- 武器类型：{weapon.weapon_type}",
        f"- 可使用超弦体：{'、'.join(weapon.users) if weapon.users else '暂无'}",
    ]
    if weapon.intro:
        lines.append(f"- 武器介绍：{weapon.intro}")
    if weapon.stats_pc:
        lines.append("")
        lines.append("## 基础面板（PC）")
        lines.extend(_format_kv_bullets(weapon.stats_pc))
    if weapon.damage_falloff_pc:
        lines.append("")
        lines.append("## 距离伤害衰减（PC）")
        lines.extend(_format_kv_bullets(weapon.damage_falloff_pc))
    if weapon.extra_notes:
        lines.append("")
        lines.append("## 特殊机制补充")
        lines.extend(f"- {note}" for note in weapon.extra_notes)
    if weapon.growth_network:
        lines.append("")
        lines.append("## 武器弦能增幅网络")
        lines.extend(_format_growth_lines(weapon.growth_network))
    if weapon.detail_stats:
        lines.append("")
        lines.append("## 武器详细弹道与换弹参数")
        lines.extend(_format_kv_bullets(weapon.detail_stats))

    ai_entity(
        KnowledgePoint(
            id=f"calabiyau_weapon_primary_{weapon.name}",
            plugin=_PLUGIN_NAME,
            title=f"{weapon.name} - 卡拉彼丘主武器数据（{weapon.weapon_type}）",
            entity=weapon.name,
            content="\n".join(lines),
            tags=["卡拉彼丘", "武器", "主武器", weapon.name, weapon.weapon_type, *weapon.users],
        )
    )


def _register_secondary_weapon_entity(weapon: _SecondaryWeaponData) -> None:
    lines: list[str] = [f"# {weapon.name} - 副武器资料（PC端）", ""]
    if weapon.obtain:
        lines.append(f"- 获取方式：{weapon.obtain}")
    if weapon.intro:
        lines.append(f"- 武器介绍：{weapon.intro}")
    if weapon.stats_pc:
        lines.append("")
        lines.append("## 基础面板（PC）")
        lines.extend(_format_kv_bullets(weapon.stats_pc))
    if weapon.damage_falloff_pc:
        lines.append("")
        lines.append("## 距离伤害衰减（PC）")
        lines.extend(_format_kv_bullets(weapon.damage_falloff_pc))

    ai_entity(
        KnowledgePoint(
            id=f"calabiyau_weapon_secondary_{weapon.name}",
            plugin=_PLUGIN_NAME,
            title=f"{weapon.name} - 卡拉彼丘副武器数据",
            entity=weapon.name,
            content="\n".join(lines),
            tags=["卡拉彼丘", "武器", "副武器", weapon.name],
        )
    )


def _register_melee_weapon_entity(weapon: _MeleeWeaponData) -> None:
    lines: list[str] = [f"# {weapon.name} - 近战武器资料（PC端）", ""]
    if weapon.obtain:
        lines.append(f"- 获取方式：{weapon.obtain}")
    if weapon.intro:
        lines.append(f"- 武器介绍：{weapon.intro}")
    if weapon.damage_pc:
        lines.append("")
        lines.append("## 近战伤害与判定（PC）")
        for key, val in weapon.damage_pc.items():
            lines.append(f"- {key}：{'；'.join(val.splitlines())}")
    if weapon.handling:
        lines.append("")
        lines.append("## 手感与连段数据")
        lines.extend(f"- {item}" for item in weapon.handling)

    ai_entity(
        KnowledgePoint(
            id=f"calabiyau_weapon_melee_{weapon.name}",
            plugin=_PLUGIN_NAME,
            title=f"{weapon.name} - 卡拉彼丘近战武器数据",
            entity=weapon.name,
            content="\n".join(lines),
            tags=["卡拉彼丘", "武器", "近战武器", weapon.name],
        )
    )


def _register_tactical_item_entity(item: _TacticalItemData) -> None:
    lines: list[str] = [f"# {item.name} - 战术道具资料（PC端）", ""]
    if item.obtain:
        lines.append(f"- 获取方式：{item.obtain}")
    if item.intro:
        lines.append(f"- 道具介绍：{item.intro}")
    if item.effect:
        lines.append("")
        lines.append("## 效果与参数")
        lines.append(item.effect)
    if item.extra_data:
        lines.append("")
        lines.append("## 补充数据")
        lines.extend(f"- {line}" for line in item.extra_data)
    if item.cooldowns_sec:
        lines.append("")
        lines.append("## 模式冷却时间")
        for mode, sec in item.cooldowns_sec.items():
            lines.append(f"- {mode}：{sec} 秒")

    ai_entity(
        KnowledgePoint(
            id=f"calabiyau_weapon_tactical_{item.name}",
            plugin=_PLUGIN_NAME,
            title=f"{item.name} - 卡拉彼丘战术道具数据",
            entity=item.name,
            content="\n".join(lines),
            tags=["卡拉彼丘", "战术道具", item.name],
        )
    )


def _register_kristall_entity(kristall: _KristallData) -> None:
    lines: list[str] = [
        f"# {kristall.name} - 晶源体资料",
        "",
        f"- 晶源体 ID：{kristall.kristall_id}",
    ]
    lines.extend(_format_kv_bullets(kristall.profile))
    if kristall.stats:
        lines.append("")
        lines.append("## 等级属性与基础伤害")
        lines.extend(_format_kv_bullets(kristall.stats))
    if kristall.skills:
        lines.append("")
        lines.append("## 晶源体技能")
        for slot, desc in kristall.skills.items():
            lines.append(f"### {slot}")
            lines.append(desc)

    ai_entity(
        KnowledgePoint(
            id=f"calabiyau_kristall_{kristall.kristall_id}",
            plugin=_PLUGIN_NAME,
            title=f"{kristall.name} - 卡拉彼丘晶源体数据与技能",
            entity=kristall.name,
            content="\n".join(lines),
            tags=["卡拉彼丘", "晶源体", "晶源感染", kristall.name],
        )
    )


def _register_from_knowledge_dir(knowledge_dir: Path) -> int:
    index = _load_model(knowledge_dir / "index.json", _KnowledgeIndex)
    manifest = index.manifest
    roles = [_load_model(_resolve_safe_path(knowledge_dir, entry.path), _RoleData) for entry in manifest.roles]
    primary_weapons = [
        _load_model(_resolve_safe_path(knowledge_dir, entry.path), _PrimaryWeaponData)
        for entry in manifest.weapons.primary
    ]
    secondary_weapons = [
        _load_model(_resolve_safe_path(knowledge_dir, entry.path), _SecondaryWeaponData)
        for entry in manifest.weapons.secondary
    ]
    melee_weapons = [
        _load_model(_resolve_safe_path(knowledge_dir, entry.path), _MeleeWeaponData) for entry in manifest.weapons.melee
    ]
    tactical_items = [
        _load_model(_resolve_safe_path(knowledge_dir, entry.path), _TacticalItemData)
        for entry in manifest.weapons.tactical
    ]
    kristall_list = [
        _load_model(_resolve_safe_path(knowledge_dir, entry.path), _KristallData) for entry in manifest.kristall
    ]

    count = _register_core_guides()

    # 全局总表 1：超弦体阵营定位与武器总表
    role_overview_lines: list[str] = ["# 卡拉彼丘超弦体图鉴与阵营定位（PC端）", ""]
    for role in roles:
        aliases = (
            "、".join(ROLE_NAMES[role.role_id][1:])
            if role.role_id in ROLE_NAMES and len(ROLE_NAMES[role.role_id]) > 1
            else "无"
        )
        faction = role.profile["阵营"] if "阵营" in role.profile else "未知"
        position = role.profile["定位"] if "定位" in role.profile else "未知"
        weapons_text = "、".join(role.available_weapons) if role.available_weapons else "未知"
        role_overview_lines.append(
            f"- **{role.name}**（ID：{role.role_id}，{faction} · {position}）"
            f"｜可用主武器：{weapons_text}｜常见别名：{aliases}"
        )
    ai_entity(
        KnowledgePoint(
            id="calabiyau_roles_overview",
            plugin=_PLUGIN_NAME,
            title="卡拉彼丘超弦体阵营定位总表",
            content="\n".join(role_overview_lines),
            tags=["卡拉彼丘", "超弦体", "角色", "阵营", "定位", "武器"],
        )
    )
    count += 1

    # 全局总表 2：全武器与战术道具索引
    weapon_overview_lines: list[str] = ["# 卡拉彼丘全武器与战术道具目录（PC端）", "", "## 主武器"]
    for pw in primary_weapons:
        users_text = "、".join(pw.users) if pw.users else "通用"
        weapon_overview_lines.append(f"- **{pw.name}**（{pw.weapon_type}）｜使用者：{users_text}")
    weapon_overview_lines.extend(["", "## 副武器"])
    for sw in secondary_weapons:
        weapon_overview_lines.append(f"- **{sw.name}**（{sw.obtain}）")
    weapon_overview_lines.extend(["", "## 近战武器"])
    for mw in melee_weapons:
        weapon_overview_lines.append(f"- **{mw.name}**（{mw.obtain}）")
    weapon_overview_lines.extend(["", "## 战术道具"])
    for ti in tactical_items:
        weapon_overview_lines.append(f"- **{ti.name}**（{ti.obtain}）")
    ai_entity(
        KnowledgePoint(
            id="calabiyau_weapons_overview",
            plugin=_PLUGIN_NAME,
            title="卡拉彼丘全武器与战术道具总表",
            content="\n".join(weapon_overview_lines),
            tags=["卡拉彼丘", "武器", "主武器", "副武器", "近战武器", "战术道具"],
        )
    )
    count += 1

    # 全局总表 3：移速表与战术道具冷却时间表
    mech_lines: list[str] = ["# 卡拉彼丘超弦体移速表与战术道具冷却时间表（PC端）", ""]
    mech_lines.append("## 未持主武器 / 持副武器 / 持战术道具移速")
    for row in index.speed_table.unarmed_or_secondary_or_tactical:
        mech_lines.append(f"- {row.state}：疾跑 {row.sprint}｜行走/腰射 {row.walk_hipfire}｜开镜 {row.ads}")
    mech_lines.extend(["", "## 持主武器移速"])
    for row in index.speed_table.holding_primary_weapon:
        mech_lines.append(
            f"- {row.weapon_type}（{row.roles}）[{row.state}]："
            f"疾跑 {row.sprint}｜行走/腰射 {row.walk_hipfire}｜开镜 {row.ads}"
        )
    mech_lines.extend(["", "## 战术道具冷却时间表"])
    for item_name, modes in index.tactical_cooldowns.items():
        cd_text = "｜".join(f"{mode} {sec}秒" for mode, sec in modes.items())
        mech_lines.append(f"- **{item_name}**：{cd_text}")

    ai_entity(
        KnowledgePoint(
            id="calabiyau_tactical_cooldowns_and_speeds",
            plugin=_PLUGIN_NAME,
            title="卡拉彼丘超弦体移速表与战术道具冷却表",
            content="\n".join(mech_lines),
            tags=["卡拉彼丘", "移速", "冷却时间", "战术道具", "极限推进", "弦区争夺"],
        )
    )
    count += 1

    for role in roles:
        count += _register_role_entities(role)
    for pw in primary_weapons:
        _register_primary_weapon_entity(pw)
        count += 1
    for sw in secondary_weapons:
        _register_secondary_weapon_entity(sw)
        count += 1
    for mw in melee_weapons:
        _register_melee_weapon_entity(mw)
        count += 1
    for ti in tactical_items:
        _register_tactical_item_entity(ti)
        count += 1
    for kr in kristall_list:
        _register_kristall_entity(kr)
        count += 1

    return count


def register_calabiyau_entities(knowledge_dir: Path | None = None) -> int:
    """注册插件知识库条目；优先读取本地资源目录中的 Wiki 结构化知识。"""
    target_dir = knowledge_dir if knowledge_dir is not None else RESOURCE_DIR / "knowledge"
    index_path = target_dir / "index.json"
    if not index_path.is_file():
        logger.warning(f"{_LOG_TAG} 未发现知识索引 {index_path}，跳过 Wiki 知识注册；请先同步资源数据")
        return _register_core_guides()
    count = _register_from_knowledge_dir(target_dir)
    logger.info(f"{_LOG_TAG} 已从资源目录注册 {count} 条知识条目")
    return count


def reload_calabiyau_entities(knowledge_dir: Path | None = None) -> int:
    """卸载本插件已登记的知识条目并按最新资源目录重新注册。"""
    unregister_entities_of_plugin(_PLUGIN_NAME)
    return register_calabiyau_entities(knowledge_dir)


async def sync_calabiyau_knowledge() -> None:
    """在资源更新后重注册知识条目并同步向量库（仅 AI 启用时执行）。"""
    if not ai_config.get_config("enable").data:
        return
    count = reload_calabiyau_entities()

    from gsuid_core.ai_core.startup import (
        is_ai_core_ready,
        wait_ai_core_ready,
        is_ai_core_initializing,
    )
    from gsuid_core.ai_core.rag.knowledge import sync_knowledge

    if not is_ai_core_ready():
        if is_ai_core_initializing():
            await wait_ai_core_ready()
        if not is_ai_core_ready():
            logger.debug(f"{_LOG_TAG} AI 核心未就绪，已跳过向量库增量同步（内存已更新 {count} 条）")
            return

    await sync_knowledge()
    logger.success(f"{_LOG_TAG} 资源变更后已完成知识向量库同步（共 {count} 条）")


register_calabiyau_entities()
