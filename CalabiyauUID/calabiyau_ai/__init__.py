"""卡拉彼丘插件 AI 能力注册入口。"""

from importlib import import_module

from gsuid_core.ai_core.configs.ai_config import ai_config

_AI_SUBMODULES: tuple[str, ...] = (
    ".knowledge",
    ".tools",
    ".agents",
)


def register_calabiyau_ai() -> None:
    """按需导入知识库、独立工具与能力代理模块，触发框架注册。"""
    for submodule in _AI_SUBMODULES:
        import_module(submodule, package=__name__)


if ai_config.get_config("enable").data:
    register_calabiyau_ai()
