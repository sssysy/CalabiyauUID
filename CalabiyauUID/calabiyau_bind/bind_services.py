"""卡拉彼丘账号绑定、解绑与查看。"""

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


async def unbind_account_by_query(
    bot_id: str,
    user_id: str,
    query: str,
) -> str:
    cleaned = query.strip()
    if is_numeric_uid(cleaned):
        return await unbind_account(bot_id, user_id, cleaned)

    binds = await CalabiyauBind.get_binds(bot_id, user_id)
    if not binds:
        return "尚未绑定卡拉彼丘账号。\n发送 kq绑定 <UID 或昵称> 进行绑定。"

    local_matches: list[str] = []
    for bind in binds:
        snapshot = await load_player_snapshot(bind.game_uid)
        if snapshot is not None and snapshot.profile["player"]["nickname"] == cleaned:
            local_matches.append(bind.game_uid)
    if len(local_matches) == 1:
        return await unbind_account(bot_id, user_id, local_matches[0])
    if len(local_matches) > 1:
        candidates = "\n".join(f"- {cleaned}（UID：{uid}）" for uid in local_matches)
        return f"已绑定多个昵称为「{cleaned}」的账号，请改用 UID 解绑：\n{candidates}"

    try:
        player_id = await resolve_player_input(cleaned)
    except DakanuError as exc:
        return f"解绑失败：{exc}"
    if player_id not in {bind.game_uid for bind in binds}:
        return f"未找到该账号的绑定：[{player_id}] {cleaned}"
    return await unbind_account(bot_id, user_id, player_id)


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
