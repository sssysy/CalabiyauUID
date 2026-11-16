"""卡拉彼丘超弦体单榜命令与卡片构建。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .ranking_services import build_board_ranking_card
from ..utils.api.dakanu import DakanuError, fetch_meta_roles
from ..utils.helper.maps import resolve_role_alias, get_role_display_names

_ROLE_USAGE_PREFIX = "请提供角色名或角色 ID，例如：kq超弦体排行 星绘 或 kq超弦体排行 146"


async def _load_role_names() -> dict[int, str]:
    remote_roles = await fetch_meta_roles()
    return {**remote_roles, **get_role_display_names()}


async def resolve_role_query(raw_query: str) -> tuple[int, str] | None:
    """按角色 ID、正式名、别名或拼音解析查询参数。"""
    query = raw_query.strip()
    if not query:
        return None

    roles = await _load_role_names()
    if query.isascii() and query.isdigit():
        role_id = int(query)
        if role_id in roles:
            return role_id, roles[role_id]
        return None

    for role_id, role_name in roles.items():
        if query == role_name:
            return role_id, role_name

    alias_role_id = resolve_role_alias(query, extra_roles=roles)
    if alias_role_id is not None and alias_role_id in roles:
        return alias_role_id, roles[alias_role_id]
    return None


async def build_role_board_ranking_card(
    role_id: int,
    role_name: str,
    *,
    use_cache: bool = True,
) -> bytes:
    """拉取指定角色前 50 名单榜并渲染卡片。"""
    return await build_board_ranking_card(
        rank_type=4,
        sub_type=role_id,
        title_override=f"角色榜 · {role_name}",
        include_floor=False,
        use_cache=use_cache,
    )


async def _build_usage_message() -> str:
    try:
        roles = await _load_role_names()
    except DakanuError as exc:
        logger.warning(f"[卡拉彼丘·超弦体排行] 获取角色列表失败：{exc}")
        roles = get_role_display_names()

    if not roles:
        return _ROLE_USAGE_PREFIX
    available_roles = "、".join(roles[role_id] for role_id in sorted(roles))
    return f"{_ROLE_USAGE_PREFIX}\n可选角色：{available_roles}"


def register_role_board_ranking(sv_ranking: SV) -> None:
    """向排行服务注册超弦体单榜命令。"""

    @sv_ranking.on_command("超弦体排行", block=True)
    async def calabiyau_role_board_ranking(bot: Bot, ev: Event) -> None:
        query = ev.text.strip()
        if not query:
            await bot.send(await _build_usage_message())
            return

        try:
            resolved = await resolve_role_query(query)
        except DakanuError as exc:
            logger.warning(f"[卡拉彼丘·超弦体排行] 解析角色参数失败：{exc}")
            await bot.send(str(exc))
            return

        if resolved is None:
            await bot.send(await _build_usage_message())
            return

        role_id, role_name = resolved
        try:
            image = await build_role_board_ranking_card(role_id, role_name)
        except DakanuError as exc:
            logger.warning(f"[卡拉彼丘·超弦体排行] 获取超弦体排行失败：{exc}")
            await bot.send(str(exc))
            return
        except RuntimeError:
            logger.exception("[卡拉彼丘·超弦体排行] 渲染卡片失败")
            await bot.send("超弦体排行卡片生成失败，请稍后再试。")
            return
        await bot.send(image)
