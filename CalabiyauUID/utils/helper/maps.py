"""从 resources/maps.json 组装地图与角色基础 ID 映射关系。"""

import json
import itertools
from pathlib import Path
from functools import lru_cache
from dataclasses import dataclass
from collections.abc import Mapping, Callable

from pypinyin import Style, pinyin, lazy_pinyin

from gsuid_core.logger import logger

from ..utils.paths import RESOURCE_DIR

MAPS_JSON_PATH: Path = RESOURCE_DIR / "maps.json"
_LOG_TAG = "[卡拉彼丘·地图角色配置]"


@dataclass(frozen=True)
class MapInfo:
    slug: str
    name: str
    mode: str


@dataclass(frozen=True)
class RoleMeta:
    role_id: int
    faction_code: int
    faction_name: str
    faction_dot_color: str
    faction_text_color: str
    position_code: int
    position_name: str


_MAPS: list[MapInfo] = []
_MAP_BY_SLUG: dict[str, MapInfo] = {}
_EXPLICIT_MAP_SLUGS: dict[int, str] = {}
_EXPLICIT_MAP_NAMES: dict[int, str] = {}
_MODE_NAMES: dict[int, str] = {}

# 保持模块级字典引用不变，重载时原地更新以兼容外部直接 import
ROLE_NAMES: dict[int, list[str]] = {}
ROLE_FACTIONS: dict[int, tuple[str, str, str]] = {}
ROLE_POSITIONS: dict[int, str] = {}
_ROLE_META_CODES: dict[int, tuple[int, int]] = {}

_loaded_path: Path | None = None
_loaded_mtime_ns: int | None = None


def _parse_int_key(raw_key: str) -> int | None:
    cleaned = raw_key.strip()
    if not cleaned.isascii() or not cleaned.isdigit():
        return None
    return int(cleaned)


def _parse_int_str_map(raw: object) -> dict[int, str]:
    if not isinstance(raw, dict):
        return {}
    result: dict[int, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        parsed_key = _parse_int_key(key)
        if parsed_key is not None and value:
            result[parsed_key] = value
    return result


def _parse_maps_list(raw: object) -> list[MapInfo]:
    if not isinstance(raw, list):
        return []
    result: list[MapInfo] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if "slug" not in item or "name" not in item or "mode" not in item:
            continue
        slug = item["slug"]
        name = item["name"]
        mode = item["mode"]
        if isinstance(slug, str) and isinstance(name, str) and isinstance(mode, str):
            result.append(MapInfo(slug=slug, name=name, mode=mode))
    return result


def _parse_role_names(raw: object) -> dict[int, list[str]]:
    if not isinstance(raw, dict):
        return {}
    result: dict[int, list[str]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, list):
            continue
        parsed_key = _parse_int_key(key)
        if parsed_key is None:
            continue
        names = [item for item in value if isinstance(item, str) and item.strip()]
        if names:
            result[parsed_key] = names
    return result


def _parse_role_factions(raw: object) -> dict[int, tuple[str, str, str]]:
    if not isinstance(raw, dict):
        return {}
    result: dict[int, tuple[str, str, str]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        parsed_key = _parse_int_key(key)
        if parsed_key is None:
            continue
        if "name" not in value or "dot_color" not in value or "text_color" not in value:
            continue
        name = value["name"]
        dot_color = value["dot_color"]
        text_color = value["text_color"]
        if isinstance(name, str) and isinstance(dot_color, str) and isinstance(text_color, str):
            result[parsed_key] = (name, dot_color, text_color)
    return result


def _parse_role_meta_codes(raw: object) -> dict[int, tuple[int, int]]:
    if not isinstance(raw, dict):
        return {}
    result: dict[int, tuple[int, int]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        parsed_key = _parse_int_key(key)
        if parsed_key is None:
            continue
        if "faction_code" not in value or "position_code" not in value:
            continue
        faction_code = value["faction_code"]
        position_code = value["position_code"]
        if (
            isinstance(faction_code, int)
            and not isinstance(faction_code, bool)
            and isinstance(position_code, int)
            and not isinstance(position_code, bool)
        ):
            result[parsed_key] = (faction_code, position_code)
    return result


def reload_maps_data(path: Path | None = None) -> bool:
    """从 resources/maps.json 重新装载并组装全部地图与角色配置表。"""
    global _loaded_path, _loaded_mtime_ns
    target = path if path is not None else MAPS_JSON_PATH
    if not target.is_file():
        logger.warning(f"{_LOG_TAG} 配置文件不存在：{target.name}")
        return False
    try:
        stat_result = target.stat()
        raw_text = target.read_text(encoding="utf-8")
        payload: object = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"{_LOG_TAG} 读取 {target.name} 失败：{exc}")
        return False

    if not isinstance(payload, dict):
        logger.warning(f"{_LOG_TAG} {target.name} 顶层结构不是对象")
        return False

    maps_list = _parse_maps_list(payload["maps"] if "maps" in payload else None)
    explicit_slugs = _parse_int_str_map(payload["explicit_map_slugs"] if "explicit_map_slugs" in payload else None)
    explicit_names = _parse_int_str_map(payload["explicit_map_names"] if "explicit_map_names" in payload else None)
    mode_names = _parse_int_str_map(payload["mode_names"] if "mode_names" in payload else None)
    role_names = _parse_role_names(payload["role_names"] if "role_names" in payload else None)
    role_factions = _parse_role_factions(payload["role_factions"] if "role_factions" in payload else None)
    role_positions = _parse_int_str_map(payload["role_positions"] if "role_positions" in payload else None)
    role_meta_codes = _parse_role_meta_codes(payload["role_meta_codes"] if "role_meta_codes" in payload else None)

    _MAPS.clear()
    _MAPS.extend(maps_list)
    _MAP_BY_SLUG.clear()
    _MAP_BY_SLUG.update({map_info.slug: map_info for map_info in maps_list})
    _EXPLICIT_MAP_SLUGS.clear()
    _EXPLICIT_MAP_SLUGS.update(explicit_slugs)
    _EXPLICIT_MAP_NAMES.clear()
    _EXPLICIT_MAP_NAMES.update(explicit_names)
    _MODE_NAMES.clear()
    _MODE_NAMES.update(mode_names)
    ROLE_NAMES.clear()
    ROLE_NAMES.update(role_names)
    ROLE_FACTIONS.clear()
    ROLE_FACTIONS.update(role_factions)
    ROLE_POSITIONS.clear()
    ROLE_POSITIONS.update(role_positions)
    _ROLE_META_CODES.clear()
    _ROLE_META_CODES.update(role_meta_codes)

    _loaded_path = target
    _loaded_mtime_ns = stat_result.st_mtime_ns
    return True


def _ensure_loaded() -> None:
    target = _loaded_path if _loaded_path is not None else MAPS_JSON_PATH
    if not target.is_file():
        return
    try:
        current_mtime_ns = target.stat().st_mtime_ns
    except OSError:
        return
    if _loaded_mtime_ns != current_mtime_ns:
        reload_maps_data(target)


def resolve_map(map_id: int) -> MapInfo | None:
    """按站点规则解析地图；无法识别时返回 None。"""
    _ensure_loaded()
    base_map: MapInfo | None = None
    if map_id in _EXPLICIT_MAP_SLUGS:
        slug = _EXPLICIT_MAP_SLUGS[map_id]
        if slug in _MAP_BY_SLUG:
            base_map = _MAP_BY_SLUG[slug]
    elif map_id > 0:
        mode_code = map_id // 100
        if mode_code in _MODE_NAMES:
            mode_name = _MODE_NAMES[mode_code]
            mode_maps = [map_info for map_info in _MAPS if map_info.mode == mode_name]
            if mode_maps:
                index = (map_id % 100 - 1) % len(mode_maps)
                base_map = mode_maps[index]

    if map_id in _EXPLICIT_MAP_NAMES:
        explicit_name = _EXPLICIT_MAP_NAMES[map_id]
        if base_map is not None:
            if base_map.name == explicit_name:
                return base_map
            return MapInfo(slug=base_map.slug, name=explicit_name, mode=base_map.mode)
        return MapInfo(slug="", name=explicit_name, mode="")

    return base_map


def resolve_role_name(role_id: int) -> str | None:
    """按角色 ID 解析基础角色名；未收录时返回 None。"""
    _ensure_loaded()
    if role_id in ROLE_NAMES and ROLE_NAMES[role_id]:
        name = ROLE_NAMES[role_id][0].strip()
        return name if name else None
    return None


def resolve_role_meta(role_id: int) -> RoleMeta | None:
    """按角色 ID 解析阵营与定位展示信息。"""
    _ensure_loaded()
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
    _ensure_loaded()
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
    _ensure_loaded()
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


reload_maps_data()
