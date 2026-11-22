"""Fanbook 网页登录 FastAPI 路由注册。"""

from __future__ import annotations

from pathlib import Path

import jinja2
from pydantic import BaseModel
from starlette.responses import HTMLResponse, JSONResponse

from gsuid_core.web_app import app

from .login_services import LOGIN_CACHE, send_fanbook_sms, submit_fanbook_login

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_TEMPLATE_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=True,
)


class _SendSmsPayload(BaseModel):
    auth: str
    areaCode: str = "86"
    mobile: str
    ticket: str
    randstr: str


class _LoginPayload(BaseModel):
    auth: str
    areaCode: str = "86"
    mobile: str
    code: str


@app.get("/kq/fanbook/i/{auth_token}")
async def fanbook_login_page(auth_token: str) -> HTMLResponse:
    state = LOGIN_CACHE.get(auth_token)
    template = _TEMPLATE_ENV.get_template("fanbook_login.html")
    if state is None:
        html = template.render(
            valid=False,
            done=False,
            auth="",
            user_id="",
            captcha_app_id="",
        )
        return HTMLResponse(html, status_code=404)

    html = template.render(
        valid=True,
        done=state.done,
        auth=auth_token,
        user_id=state.user_id,
        captcha_app_id=state.captcha_app_id,
    )
    return HTMLResponse(html)


@app.post("/kq/fanbook/sendSmsCode")
async def fanbook_send_sms(payload: _SendSmsPayload) -> JSONResponse:
    ok, msg = await send_fanbook_sms(
        auth_token=payload.auth,
        area_code=payload.areaCode,
        mobile=payload.mobile,
        ticket=payload.ticket,
        rand_str=payload.randstr,
    )
    return JSONResponse({"ok": ok, "msg": msg}, status_code=200 if ok else 400)


@app.post("/kq/fanbook/login")
async def fanbook_perform_login(payload: _LoginPayload) -> JSONResponse:
    ok, msg = await submit_fanbook_login(
        auth_token=payload.auth,
        area_code=payload.areaCode,
        mobile=payload.mobile,
        sms_code=payload.code,
    )
    return JSONResponse({"ok": ok, "msg": msg}, status_code=200 if ok else 400)
