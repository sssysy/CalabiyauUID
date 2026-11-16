"""地图与角色等基础 ID 映射关系。"""

import itertools
from functools import lru_cache
from dataclasses import dataclass
from collections.abc import Mapping, Callable

from pypinyin import Style, pinyin, lazy_pinyin


@dataclass(frozen=True)
class MapInfo:
    slug: str
    name: str
    mode: str


_MAPS: tuple[MapInfo, ...] = (
    MapInfo("map-01", "404基地", "爆破模式"),
    MapInfo("map-02", "88区", "爆破模式"),
    MapInfo("map-03", "欧拉港口", "爆破模式"),
    MapInfo("map-04", "风曳镇", "爆破模式"),
    MapInfo("map-05", "空间实验室", "爆破模式"),
    MapInfo("map-06", "柯西街区", "爆破模式"),
    MapInfo("map-07", "科斯迷特", "爆破模式"),
    MapInfo("map-08", "2号仓库", "团竞模式"),
    MapInfo("map-09", "鹿鹿潮玩区", "团竞模式"),
    MapInfo("map-10", "水下发电厂", "团竞模式"),
    MapInfo("map-11", "码头小镇", "团竞模式"),
    MapInfo("map-12", "花明弓道馆", "团竞模式"),
    MapInfo("map-13", "离境区", "推车模式"),
    MapInfo("map-14", "亚克萨工厂", "推车模式"),
    MapInfo("map-15", "簌雪东区", "推车模式"),
    MapInfo("map-16", "洛希街区", "晶源感染"),
    MapInfo("map-17", "迦纳古城", "晶源感染"),
    MapInfo("map-18", "极地研究所", "晶源感染"),
    MapInfo("map-19", "奥卡努斯", "爆破模式"),
    MapInfo("map-20", "莱布伦城", "爆破模式"),
)

_MAP_BY_SLUG: dict[str, MapInfo] = {map_info.slug: map_info for map_info in _MAPS}
_EXPLICIT_MAP_SLUGS: dict[int, str] = {
    200: "map-01",
    201: "map-02",
    202: "map-03",
    203: "map-05",
    204: "map-04",
    205: "map-06",
    206: "map-07",
    207: "map-19",
    208: "map-20",
    11001: "map-16",
    11002: "map-17",
    11003: "map-18",
    11004: "map-05",
    11005: "map-03",
    11006: "map-18",
}
_MODE_NAMES: dict[int, str] = {
    1: "团竞模式",
    2: "爆破模式",
    3: "推车模式",
    4: "晶源感染",
    5: "晶源感染",
    9: "晶源感染",
    30: "团竞模式",
}


def resolve_map(map_id: int) -> MapInfo | None:
    """按站点规则解析地图；无法识别时返回 None。"""
    if map_id in _EXPLICIT_MAP_SLUGS:
        slug = _EXPLICIT_MAP_SLUGS[map_id]
        if slug in _MAP_BY_SLUG:
            return _MAP_BY_SLUG[slug]
        return None

    mode_code = map_id // 100
    if mode_code not in _MODE_NAMES:
        return None
    mode_name = _MODE_NAMES[mode_code]
    mode_maps = [map_info for map_info in _MAPS if map_info.mode == mode_name]
    if not mode_maps:
        return None
    index = (map_id % 100 - 1) % len(mode_maps)
    return mode_maps[index]


ROLE_NAMES: dict[int, list[str]] = {
    101: ["米雪儿·李", "猫", "猫猫", "糖猫", "唐猫", "米雪儿"],
    105: ["奥黛丽·格罗夫", "机枪", "机枪妹", "奥黛丽"],
    107: ["玛德蕾娜·利里", "小画家", "颜料泡泡", "玛德蕾娜"],
    108: ["信", "牢信"],
    109: ["令", "牢令", "问了吗", "问了么"],
    110: ["白墨", "男喷", "墨老板", "自由意志"],
    112: ["绯莎", "鲨鱼"],
    115: ["芙拉薇娅", "蝴蝶"],
    119: ["艾卡", "女高", "女高中生"],
    120: ["珐格兰丝", "调香师", "调香", "香水"],
    121: ["忧雾", "窝窝", "蜗牛", "蜗蜗"],
    122: ["玛拉", "麻辣"],
    123: ["蕾欧娜", "土木学姐", "土木学长", "土木"],
    124: ["心夏", "心夏妈妈", "妈妈"],
    125: ["千代"],
    126: ["诺诺"],
    128: ["拉薇", "辣味"],
    130: ["汐"],
    131: ["伊薇特", "小熊", "熊", "菲"],
    132: ["明", "牢明", "牢大", "老大"],
    133: ["梅瑞狄斯", "沙猫"],
    137: ["香奈美", "小美", "歌姬"],
    146: ["星绘", "小绘", "守护星芒"],
    205: ["加拉蒂亚·利里", "大画家", "加拉蒂亚"],
}


def resolve_role_name(role_id: int) -> str | None:
    """按角色 ID 解析基础角色名；未收录时返回 None。"""
    if role_id in ROLE_NAMES and ROLE_NAMES[role_id]:
        name = ROLE_NAMES[role_id][0].strip()
        return name if name else None
    return None


@dataclass(frozen=True)
class RoleMeta:
    role_id: int
    faction_code: int
    faction_name: str
    faction_dot_color: str
    faction_text_color: str
    position_code: int
    position_name: str


ROLE_FACTIONS: dict[int, tuple[str, str, str]] = {
    1: ("欧泊", "#386CF4", "#2558D9"),
    2: ("剪刀手", "#FD383F", "#CF2E35"),
    4: ("乌尔比诺", "#FFB526", "#B87300"),
}

ROLE_POSITIONS: dict[int, str] = {
    1: "守护",
    2: "决斗",
    3: "控场",
    4: "支援",
    6: "先锋",
}

_ROLE_META_CODES: dict[int, tuple[int, int]] = {
    101: (1, 1),
    105: (4, 1),
    107: (4, 3),
    108: (1, 1),
    109: (2, 3),
    110: (4, 2),
    112: (4, 2),
    115: (1, 2),
    119: (2, 2),
    120: (2, 4),
    121: (1, 3),
    122: (2, 2),
    123: (1, 1),
    124: (1, 4),
    125: (1, 2),
    126: (2, 6),
    128: (2, 6),
    130: (4, 2),
    131: (1, 3),
    132: (2, 2),
    133: (2, 3),
    137: (2, 6),
    146: (4, 4),
    205: (4, 6),
}


def resolve_role_meta(role_id: int) -> RoleMeta | None:
    """按角色 ID 解析阵营与定位展示信息。"""
    if role_id not in _ROLE_META_CODES:
        return None
    faction_code, position_code = _ROLE_META_CODES[role_id]
    faction_name = ""
    faction_dot_color = ""
    faction_text_color = ""
    if faction_code in ROLE_FACTIONS:
        faction_name, faction_dot_color, faction_text_color = ROLE_FACTIONS[faction_code]
    position_name = ROLE_POSITIONS[position_code] if position_code in ROLE_POSITIONS else ""
    return RoleMeta(
        role_id=role_id,
        faction_code=faction_code,
        faction_name=faction_name,
        faction_dot_color=faction_dot_color,
        faction_text_color=faction_text_color,
        position_code=position_code,
        position_name=position_name,
    )


def get_role_display_names() -> dict[int, str]:
    """提取基础角色 ID 到正式展示名的映射。"""
    display_names: dict[int, str] = {}
    for role_id, names in ROLE_NAMES.items():
        if not names:
            continue
        name = names[0].strip()
        if name:
            display_names[role_id] = name
    return display_names


@dataclass(frozen=True)
class _PinyinVariants:
    default_full: str
    default_initials: str
    heteronym_full: tuple[str, ...]
    heteronym_initials: tuple[str, ...]


def _normalize_role_token(text: str) -> str:
    return "".join(text.split()).replace("·", "").replace("•", "").casefold()


def _expand_pinyin(syllables: list[list[str]], *, limit: int = 64) -> tuple[str, ...]:
    unique_slots = [list(dict.fromkeys(item.casefold() for item in slot if item)) for slot in syllables]
    if not unique_slots or any(not slot for slot in unique_slots):
        return ()
    combos = ("".join(parts) for parts in itertools.product(*unique_slots))
    return tuple(itertools.islice(combos, limit))


@lru_cache(maxsize=512)
def _extract_pinyin_variants(normalized: str) -> _PinyinVariants:
    default_full = "".join(lazy_pinyin(normalized)).casefold()
    default_initials = "".join(lazy_pinyin(normalized, style=Style.FIRST_LETTER)).casefold()
    heteronym_full = _expand_pinyin(pinyin(normalized, style=Style.NORMAL, heteronym=True))
    heteronym_initials = _expand_pinyin(pinyin(normalized, style=Style.FIRST_LETTER, heteronym=True))
    return _PinyinVariants(
        default_full=default_full,
        default_initials=default_initials,
        heteronym_full=heteronym_full,
        heteronym_initials=heteronym_initials,
    )


def _build_role_candidates(raw_names: list[str]) -> tuple[str, ...]:
    candidates: list[str] = []
    for raw_name in raw_names:
        cleaned = raw_name.strip()
        if not cleaned:
            continue
        raw_variants = [cleaned]
        if "·" in cleaned:
            prefix = cleaned.split("·", 1)[0].strip()
            if prefix:
                raw_variants.append(prefix)
        for variant in raw_variants:
            normalized = _normalize_role_token(variant)
            if normalized and normalized not in candidates:
                candidates.append(normalized)
    return tuple(candidates)


def _collect_role_entries(
    extra_roles: Mapping[int, str] | None,
) -> list[tuple[int, tuple[str, ...]]]:
    entries: list[tuple[int, tuple[str, ...]]] = []
    if extra_roles is None:
        for role_id, names in ROLE_NAMES.items():
            entries.append((role_id, _build_role_candidates(names)))
        return entries

    for role_id, names in ROLE_NAMES.items():
        if role_id not in extra_roles:
            continue
        merged = list(names)
        remote_name = extra_roles[role_id].strip()
        if remote_name and remote_name not in merged:
            merged.append(remote_name)
        entries.append((role_id, _build_role_candidates(merged)))
    for role_id, role_name in extra_roles.items():
        if role_id not in ROLE_NAMES:
            entries.append((role_id, _build_role_candidates([role_name])))
    return entries


def resolve_role_alias(
    query: str,
    extra_roles: Mapping[int, str] | None = None,
) -> int | None:
    """按正式名、别名、拼音或首字母解析角色 ID；冲突时取首个命中。"""
    normalized_query = _normalize_role_token(query)
    if not normalized_query:
        return None

    entries = _collect_role_entries(extra_roles)
    for role_id, candidates in entries:
        if normalized_query in candidates:
            return role_id

    pinyin_pairs = [
        (role_id, _extract_pinyin_variants(candidate))
        for role_id, candidates in entries
        for candidate in candidates
        if not candidate.isascii()
    ]
    matchers: tuple[Callable[[_PinyinVariants], bool], ...] = (
        lambda variants: normalized_query == variants.default_full,
        lambda variants: normalized_query == variants.default_initials,
        lambda variants: normalized_query in variants.heteronym_full,
        lambda variants: normalized_query in variants.heteronym_initials,
    )
    for matcher in matchers:
        for role_id, variants in pinyin_pairs:
            if matcher(variants):
                return role_id
    return None
