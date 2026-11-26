"""卡拉彼丘 Fanbook 登录与登出命令。"""

from gsuid_core.sv import SV
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.server import on_core_start

from . import login_router
from .login_services import (
    logout_fanbook,
    request_fanbook_login,
    refresh_expiring_fanbook_tokens,
    schedule_startup_fanbook_refresh,
)

_ = login_router  # 触发 FastAPI 登录页面与接口路由注册

sv_fanbook_login = SV("卡拉彼丘Fanbook登录")


@sv_fanbook_login.on_fullmatch("登录", block=True)
async def calabiyau_fanbook_login(bot: Bot, ev: Event) -> None:
    await request_fanbook_login(bot, ev)


@sv_fanbook_login.on_fullmatch(("登出", "退出"), block=True)
async def calabiyau_fanbook_logout(bot: Bot, ev: Event) -> None:
    await logout_fanbook(bot, ev)


@scheduler.scheduled_job("interval", hours=12, id="klbq_fanbook_token_refresh", replace_existing=True)
async def scheduled_fanbook_token_refresh() -> None:
    await refresh_expiring_fanbook_tokens()


@on_core_start
async def on_start_fanbook_token_refresh() -> None:
    schedule_startup_fanbook_refresh()
