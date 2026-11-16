"""卡拉彼丘活动结束提醒去重记录表。"""

from typing import TypeVar

from sqlmodel import Field, col, select
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.utils.database.base_models import BaseIDModel, with_session, with_read_session

T_CalabiyauActivityRemind = TypeVar(
    "T_CalabiyauActivityRemind",
    bound="CalabiyauActivityRemind",
)


class CalabiyauActivityRemind(BaseIDModel, table=True):
    """记录已发送过 24 小时结束提醒的活动，防止重启或轮询重复推送。"""

    activity_key: str = Field(default="", unique=True, index=True, title="活动标识")
    end_at_ts: int = Field(default=0, title="活动结束时间戳")
    reminded_at_ts: int = Field(default=0, title="提醒发送时间戳")

    @classmethod
    @with_read_session
    async def get_reminded_map(
        cls: type[T_CalabiyauActivityRemind],
        session: AsyncSession,
    ) -> dict[str, int]:
        result = await session.execute(select(cls))
        rows = list(result.scalars().all())
        return {row.activity_key: row.end_at_ts for row in rows if row.activity_key}

    @classmethod
    @with_session
    async def mark_reminded(
        cls: type[T_CalabiyauActivityRemind],
        session: AsyncSession,
        entries: list[tuple[str, int]],
        reminded_at_ts: int,
    ) -> None:
        if not entries:
            return
        keys = [entry[0] for entry in entries]
        result = await session.execute(select(cls).where(col(cls.activity_key).in_(keys)))
        existing = {row.activity_key: row for row in result.scalars().all()}
        for activity_key, end_at_ts in entries:
            if activity_key in existing:
                record = existing[activity_key]
                record.end_at_ts = end_at_ts
                record.reminded_at_ts = reminded_at_ts
            else:
                session.add(
                    cls(
                        activity_key=activity_key,
                        end_at_ts=end_at_ts,
                        reminded_at_ts=reminded_at_ts,
                    )
                )

    @classmethod
    @with_session
    async def prune_expired(
        cls: type[T_CalabiyauActivityRemind],
        session: AsyncSession,
        cutoff_ts: int,
    ) -> None:
        await session.execute(delete(cls).where(col(cls.end_at_ts) < cutoff_ts))
