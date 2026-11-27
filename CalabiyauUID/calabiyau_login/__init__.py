"""卡拉彼丘 Fanbook 登录与登出命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from . import login_router
from .login_common import (
    logout_fanbook,
    refresh_fanbook_token,
)
from .web_login_services import request_fanbook_login
from .qrcode_login_services import request_fanbook_qrcode_login

_ = login_router  # 触发 FastAPI 登录页面与接口路由注册

sv_fanbook_login = SV("卡拉彼丘Fanbook登录")


@sv_fanbook_login.on_fullmatch("登录", block=True)
async def calabiyau_fanbook_login(bot: Bot, ev: Event) -> None:
    await request_fanbook_login(bot, ev)


@sv_fanbook_login.on_fullmatch("扫码登录", block=True)
async def calabiyau_fanbook_qrcode_login(bot: Bot, ev: Event) -> None:
    await request_fanbook_qrcode_login(bot, ev)


@sv_fanbook_login.on_fullmatch(("登出", "退出"), block=True)
async def calabiyau_fanbook_logout(bot: Bot, ev: Event) -> None:
    await logout_fanbook(bot, ev)


@sv_fanbook_login.on_fullmatch("刷新令牌", block=True)
async def calabiyau_fanbook_refresh_token(bot: Bot, ev: Event) -> None:
    await refresh_fanbook_token(bot, ev)
