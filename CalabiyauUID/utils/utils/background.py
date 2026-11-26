"""插件后台任务统一追踪与停机取消。"""

import asyncio
from typing import Protocol
from dataclasses import dataclass

from gsuid_core.logger import logger

_SHUTDOWN_TIMEOUT_SECONDS = 5.0


class TrackedTask(Protocol):
    """后台任务最小控制协议，避免 asyncio.Task 泛型不变性限制。"""

    def done(self) -> bool: ...
    def cancel(self, msg: object = None) -> bool: ...
    def get_name(self) -> str: ...


@dataclass(frozen=True, slots=True)
class _TrackedEntry:
    task: TrackedTask
    done_event: asyncio.Event


_tracked_tasks: dict[int, _TrackedEntry] = {}


def track_background_task[ValueT](
    task: asyncio.Task[ValueT],
    *,
    log_tag: str = "",
    error_label: str = "后台任务异常",
) -> asyncio.Task[ValueT]:
    """登记后台任务强引用，在完成时自动移除并按需记录未捕获异常。"""
    task_id = id(task)
    done_event = asyncio.Event()
    _tracked_tasks[task_id] = _TrackedEntry(task=task, done_event=done_event)

    def _on_done(finished: asyncio.Task[ValueT]) -> None:
        _tracked_tasks.pop(task_id, None)
        done_event.set()
        if finished.cancelled():
            return
        exc = finished.exception()
        if exc is not None and log_tag:
            logger.warning(f"{log_tag} {error_label}：{exc!r}")

    task.add_done_callback(_on_done)
    return task


def active_background_task_count() -> int:
    """返回当前仍在运行中的后台任务数量。"""
    return len(_tracked_tasks)


async def cancel_all_background_tasks(*, timeout: float = _SHUTDOWN_TIMEOUT_SECONDS) -> int:
    """取消并等待全部在途后台任务收尾，返回实际取消数量。"""
    pending = [entry for entry in list(_tracked_tasks.values()) if not entry.task.done()]
    if not pending:
        return 0
    for entry in pending:
        entry.task.cancel()
    try:
        await asyncio.wait_for(
            asyncio.gather(*(entry.done_event.wait() for entry in pending)),
            timeout=timeout,
        )
    except TimeoutError:
        still_running = [entry.task.get_name() for entry in pending if not entry.task.done()]
        logger.warning(f"[卡拉彼丘·缓存清理] 停机取消后台任务超时，仍有未结束任务：{still_running}")
    return len(pending)
