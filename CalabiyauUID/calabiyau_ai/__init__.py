"""卡拉彼丘插件 AI 能力注册入口。"""

from importlib import import_module

from gsuid_core.ai_core.register import on_ai_register

_AI_SUBMODULES: tuple[str, ...] = (
    ".knowledge",
    ".tools",
    ".agents",
)


@on_ai_register
def register_calabiyau_ai() -> None:
    """按需导入知识库、独立工具与能力代理模块，触发框架注册。"""
    for submodule in _AI_SUBMODULES:
        import_module(submodule, package=__name__)
