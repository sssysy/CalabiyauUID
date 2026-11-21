"""卡拉彼丘赛季参数解析与历史赛季档案拼装。"""

import re
from dataclasses import dataclass

from ..api.dakanu import (
    DakanuMeta,
    DakanuRank,
    DakanuError,
    DakanuProfile,
    DakanuPlayerSeason,
    DakanuRankingSeasons,
    fetch_ranking_seasons,
)

_S_EP_RE = re.compile(r"^s(\d+)ep(\d+)$", re.IGNORECASE)
_SP_RE = re.compile(r"^(\d+)sp(\d+)$", re.IGNORECASE)
_S_ONLY_RE = re.compile(r"^s(\d+)$", re.IGNORECASE)
_LABEL_S_EP_RE = re.compile(r"^S(\d+)EP(\d+)$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ResolvedSeason:
    season_id: int
    label: str
    current: bool
    rank_types: tuple[int, ...] = ()


def is_season_token(token: str) -> bool:
    """判断单个词元是否符合 s26ep6 / 26sp6 / s26 三种赛季输入形态。"""
    cleaned = token.strip()
    if not cleaned:
        return False
    return bool(_S_EP_RE.fullmatch(cleaned) or _SP_RE.fullmatch(cleaned) or _S_ONLY_RE.fullmatch(cleaned))


def split_season_and_target(raw_text: str) -> tuple[str | None, str]:
    """从参数文本中提取可选赛季名与剩余目标文本（UID/昵称或角色名）。"""
    cleaned = raw_text.strip()
    if not cleaned:
        return None, ""
    parts = cleaned.split()
    if len(parts) == 1:
        if is_season_token(parts[0]):
            return parts[0], ""
        return None, parts[0]
    if is_season_token(parts[0]):
        return parts[0], " ".join(parts[1:])
    if is_season_token(parts[-1]):
        return parts[-1], " ".join(parts[:-1])
    return None, cleaned


def _catalog_entries(catalog: DakanuRankingSeasons) -> list[ResolvedSeason]:
    entries: list[ResolvedSeason] = [
        ResolvedSeason(
            season_id=catalog["current"]["season_id"],
            label=catalog["current"]["label"],
            current=catalog["current"]["current"],
        )
    ]
    for item in catalog["seasons"]:
        entries.append(
            ResolvedSeason(
                season_id=item["season_id"],
                label=item["label"],
                current=item["current"],
                rank_types=tuple(item["rank_types"]),
            )
        )
    return entries


def _find_by_label(entries: list[ResolvedSeason], target_upper: str) -> ResolvedSeason | None:
    for entry in entries:
        if entry.label.upper() == target_upper:
            return entry
    return None


def resolve_season_from_catalog(raw_season: str, catalog: DakanuRankingSeasons) -> ResolvedSeason:
    """按 `/api/rankings/seasons` 目录解析赛季输入，未命中则抛出明确提示。"""
    cleaned = raw_season.strip()
    if not cleaned:
        raise DakanuError("未找到赛季 []")

    entries = _catalog_entries(catalog)
    upper = cleaned.upper()

    direct = _find_by_label(entries, upper)
    if direct is not None:
        return direct

    sp_match = _SP_RE.fullmatch(cleaned)
    if sp_match is not None:
        normalized = f"S{int(sp_match.group(1))}EP{int(sp_match.group(2))}"
        matched = _find_by_label(entries, normalized)
        if matched is not None:
            return matched
        raise DakanuError(f"未找到赛季 [{cleaned}]")

    s_ep_match = _S_EP_RE.fullmatch(cleaned)
    if s_ep_match is not None:
        normalized = f"S{int(s_ep_match.group(1))}EP{int(s_ep_match.group(2))}"
        matched = _find_by_label(entries, normalized)
        if matched is not None:
            return matched
        raise DakanuError(f"未找到赛季 [{cleaned}]")

    s_only_match = _S_ONLY_RE.fullmatch(cleaned)
    if s_only_match is not None:
        season_num = int(s_only_match.group(1))
        exact_s = _find_by_label(entries, f"S{season_num}")
        if exact_s is not None:
            return exact_s

        candidates: list[tuple[int, int, int, ResolvedSeason]] = []
        for entry in entries:
            label_match = _LABEL_S_EP_RE.fullmatch(entry.label)
            if label_match is None or int(label_match.group(1)) != season_num:
                continue
            ep_num = int(label_match.group(2))
            candidates.append((1 if entry.current else 0, ep_num, entry.season_id, entry))
        if candidates:
            candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
            return candidates[0][3]

    raise DakanuError(f"未找到赛季 [{cleaned}]")


async def resolve_season_query(raw_season: str) -> ResolvedSeason:
    """从 `/api/rankings/seasons` 实时解析用户输入的赛季名。"""
    catalog = await fetch_ranking_seasons()
    return resolve_season_from_catalog(raw_season, catalog)


def _first_positive(*values: int | None) -> int:
    for value in values:
        if value is not None and value > 0:
            return value
    return 0


def _first_positive_opt(*values: int | None) -> int | None:
    for value in values:
        if value is not None and value > 0:
            return value
    return None


def build_season_profile(profile: DakanuProfile, season: DakanuPlayerSeason) -> DakanuProfile:
    """将历史赛季数据覆盖到玩家基础档案上，保留玩家资料并清空无历史数据的区块。"""
    base_rank = profile["rank"]
    final_point = season["final"]
    top_point = season["top"]
    season_rank: DakanuRank = {
        "segment": _first_positive(final_point["segment"], top_point["segment"]),
        "topSegment": _first_positive(top_point["segment"], final_point["segment"]),
        "historicalSegment": _first_positive(season["historicalTopSegment"], base_rank["historicalSegment"]),
        "historicalSegmentSeason": base_rank["historicalSegmentSeason"],
        "historicalSegmentPos": _first_positive_opt(
            season["historicalTopPosition"],
            base_rank["historicalSegmentPos"],
        ),
        "divisionScore": _first_positive(final_point["divisionScore"], top_point["divisionScore"]),
        "topDivisionScore": base_rank["topDivisionScore"],
        "gradeScore": _first_positive(final_point["gradeScore"], top_point["gradeScore"]),
        "topGradeScore": base_rank["topGradeScore"],
        "rankPos": _first_positive_opt(final_point["rankPosition"], top_point["rankPosition"]),
        "topRankPos": _first_positive_opt(top_point["rankPosition"], final_point["rankPosition"]),
        "likeCount": base_rank["likeCount"],
    }
    base_meta = profile["meta"]
    season_meta: DakanuMeta = {
        "cached": base_meta["cached"],
        "source": "season",
        "currentSeason": season["seasonLabel"],
        "matchesTotal": 0,
        "detailsAvailable": 0,
        "warnings": [],
        "fetchedAt": base_meta["fetchedAt"],
        "stale": None,
        "observedMatches": 0,
        "lastCheckedAt": base_meta["lastCheckedAt"],
    }
    return {
        "player": profile["player"],
        "presence": profile["presence"],
        "rank": season_rank,
        "summary": season["summary"],
        "modes": season["modes"],
        "roles": season["roles"],
        "matches": [],
        "historyMatches": [],
        "teamUps": [],
        "rivals": [],
        "meta": season_meta,
    }
