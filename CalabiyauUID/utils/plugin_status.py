"""注册 CalabiyauUID 的 core状态 指标。"""

from pathlib import Path

from PIL import Image

from gsuid_core.status.plugin_status import register_status

from .database.model_bind import CalabiyauBind
from .database.model_fanbook import CalabiyauFanbookUser
from .helper.subscribe_common import SIGN_SUBSCRIBE_TASK_NAME, get_all_subscribers

_PLUGIN_NAME = "CalabiyauUID"
_PLUGIN_ICON_PATH: Path = Path(__file__).resolve().parents[2] / "ICON.png"


def _load_plugin_icon() -> Image.Image:
    with Image.open(_PLUGIN_ICON_PATH) as img:
        return img.copy()


async def _get_bind_count() -> int:
    return await CalabiyauBind.count_all()


async def _get_fanbook_account_count() -> int:
    return await CalabiyauFanbookUser.count_all()


async def _get_auto_sign_subscribe_count() -> int:
    return len(await get_all_subscribers(SIGN_SUBSCRIBE_TASK_NAME))


def register_calabiyau_status() -> None:
    """向 core状态 注册绑定数、Fanbook 账号数和自动签到订阅数。"""
    register_status(
        _load_plugin_icon(),
        _PLUGIN_NAME,
        {
            "绑定账号": _get_bind_count,
            "Fanbook 账号数": _get_fanbook_account_count,
            "订阅数量": _get_auto_sign_subscribe_count,
        },
    )
