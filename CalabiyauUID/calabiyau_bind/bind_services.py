"""卡拉彼丘账号绑定、解绑、查看与切换。"""

from ..utils.api.dakanu import DakanuError
from ..utils.helper.refresh import refresh_player_data
from ..utils.helper.player_data import load_player_snapshot
from ..utils.database.model_bind import CalabiyauBind
from ..utils.helper.player_resolve import is_numeric_uid, resolve_player_input


async def bind_account(
    bot_id: str,
    user_id: str,
    game_uid: str,
) -> str:
    result = await refresh_player_data(game_uid)
    added = await CalabiyauBind.add_bind(bot_id, user_id, game_uid)
    source = "本地快照" if result.from_cache else "最新战绩"
    nickname = result.snapshot.profile["player"]["nickname"]
    account = f"[{game_uid}] {nickname}"
    if not added:
        return f"该账号已绑定：{account}\n{source}已准备就绪。"
    return f"绑定成功：{account} 已设为当前账号。\n{source}已保存。"


async def unbind_account(
    bot_id: str,
    user_id: str,
    game_uid: str,
) -> str:
    deleted, was_main, current_main = await CalabiyauBind.delete_bind(bot_id, user_id, game_uid)
    if not deleted:
        return f"未找到该账号的绑定：[{game_uid}]"
    if current_main is None:
        return f"已解绑：[{game_uid}]\n当前暂无绑定账号。"
    if not was_main:
        return f"已解绑：[{game_uid}]\n当前账号仍为：[{current_main}]"
    return f"已解绑：[{game_uid}]\n当前账号已切换为：[{current_main}]"


async def _format_bound_account(game_uid: str) -> str:
    snapshot = await load_player_snapshot(game_uid)
    if snapshot is None:
        return f"[{game_uid}]"
    nickname = snapshot.profile["player"]["nickname"]
    return f"[{game_uid}] {nickname}"


async def _resolve_bound_uid(
    bot_id: str,
    user_id: str,
    query: str,
    action_label: str,
) -> tuple[str | None, str | None]:
    cleaned = query.strip()
    if is_numeric_uid(cleaned):
        return cleaned, None

    binds = await CalabiyauBind.get_binds(bot_id, user_id)
    if not binds:
        return None, "尚未绑定卡拉彼丘账号。\n发送 kq绑定 <UID 或昵称> 进行绑定。"

    local_matches: list[str] = []
    for bind in binds:
        snapshot = await load_player_snapshot(bind.game_uid)
        if snapshot is not None and snapshot.profile["player"]["nickname"] == cleaned:
            local_matches.append(bind.game_uid)
    if len(local_matches) == 1:
        return local_matches[0], None
    if len(local_matches) > 1:
        candidates = "\n".join(f"- {cleaned}（UID：{uid}）" for uid in local_matches)
        return None, f"已绑定多个昵称为「{cleaned}」的账号，请改用 UID {action_label}：\n{candidates}"

    try:
        player_id = await resolve_player_input(cleaned)
    except DakanuError as exc:
        return None, f"{action_label}失败：{exc}"
    if player_id not in {bind.game_uid for bind in binds}:
        return None, f"未找到该账号的绑定：[{player_id}] {cleaned}"
    return player_id, None


async def unbind_account_by_query(
    bot_id: str,
    user_id: str,
    query: str,
) -> str:
    target_uid, error_message = await _resolve_bound_uid(bot_id, user_id, query, "解绑")
    if target_uid is None:
        assert error_message is not None
        return error_message
    return await unbind_account(bot_id, user_id, target_uid)


async def switch_account(
    bot_id: str,
    user_id: str,
    query: str = "",
) -> str:
    cleaned = query.strip()
    target_uid: str | None = None
    if cleaned:
        target_uid, error_message = await _resolve_bound_uid(bot_id, user_id, cleaned, "切换")
        if target_uid is None:
            assert error_message is not None
            return error_message

    result = await CalabiyauBind.switch_bind(bot_id, user_id, target_uid)
    if result.status == "no_binds":
        return "尚未绑定卡拉彼丘账号。\n发送 kq绑定 <UID 或昵称> 进行绑定。"
    if result.status == "not_found":
        assert result.game_uid is not None
        return f"未找到该账号的绑定：[{result.game_uid}]"
    assert result.game_uid is not None
    account = await _format_bound_account(result.game_uid)
    if result.status == "single_bind":
        return f"当前仅绑定 1 个账号：{account}，无需切换。"
    if result.status == "already_main":
        return f"当前账号已是：{account}"
    return f"已切换当前账号为：{account}"


async def view_accounts(
    bot_id: str,
    user_id: str,
) -> str:
    binds = await CalabiyauBind.get_binds(bot_id, user_id)
    if not binds:
        return "尚未绑定卡拉彼丘账号。\n发送 kq绑定 <UID 或昵称> 进行绑定。"

    lines = [f"已绑定 {len(binds)} 个卡拉彼丘账号："]
    for index, bind in enumerate(binds, start=1):
        suffix = " [当前账号]" if bind.is_main else ""
        lines.append(f"{index}. {bind.game_uid}{suffix}")
    return "\n".join(lines)
