"""卡拉彼丘兑换码订阅推送去重记录表。"""

from typing import TypeVar
from dataclasses import dataclass

from sqlmodel import Field, col, select
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.utils.database.base_models import BaseIDModel, with_session, with_read_session

T_CalabiyauCdkeyRemind = TypeVar(
    "T_CalabiyauCdkeyRemind",
    bound="CalabiyauCdkeyRemind",
)


@dataclass(frozen=True)
class CdkeyRemindState:
    """单个兑换码的推送去重状态。"""

    expires_at_ts: int
    is_permanent: bool
    new_notified: bool
    expiring_notified: bool


class CalabiyauCdkeyRemind(BaseIDModel, table=True):
    """记录已推送过的新上线兑换码与 24 小时临期提醒，防止重复推送。"""

    __table_args__ = {"extend_existing": True}

    code: str = Field(default="", unique=True, index=True, title="兑换码")
    expires_at_ts: int = Field(default=0, title="兑换码失效时间戳")
    is_permanent: bool = Field(default=False, title="是否常驻")
    new_notified_at_ts: int = Field(default=0, title="新码推送时间戳")
    expiring_notified_at_ts: int = Field(default=0, title="临期提醒时间戳")

    @classmethod
    @with_read_session
    async def get_state_map(
        cls: type[T_CalabiyauCdkeyRemind],
        session: AsyncSession,
    ) -> dict[str, CdkeyRemindState]:
        result = await session.execute(select(cls))
        rows = list(result.scalars().all())
        return {
            row.code: CdkeyRemindState(
                expires_at_ts=row.expires_at_ts,
                is_permanent=row.is_permanent,
                new_notified=row.new_notified_at_ts > 0,
                expiring_notified=row.expiring_notified_at_ts > 0,
            )
            for row in rows
            if row.code
        }

    @classmethod
    @with_session
    async def mark_new_notified(
        cls: type[T_CalabiyauCdkeyRemind],
        session: AsyncSession,
        entries: list[tuple[str, int, bool]],
        notified_at_ts: int,
    ) -> None:
        if not entries:
            return
        codes = [entry[0] for entry in entries]
        result = await session.execute(select(cls).where(col(cls.code).in_(codes)))
        existing = {row.code: row for row in result.scalars().all()}
        for code, expires_at_ts, is_permanent in entries:
            if code in existing:
                record = existing[code]
                if record.expires_at_ts != expires_at_ts:
                    record.expiring_notified_at_ts = 0
                record.expires_at_ts = expires_at_ts
                record.is_permanent = is_permanent
                record.new_notified_at_ts = notified_at_ts
            else:
                session.add(
                    cls(
                        code=code,
                        expires_at_ts=expires_at_ts,
                        is_permanent=is_permanent,
                        new_notified_at_ts=notified_at_ts,
                        expiring_notified_at_ts=0,
                    )
                )

    @classmethod
    @with_session
    async def mark_expiring_notified(
        cls: type[T_CalabiyauCdkeyRemind],
        session: AsyncSession,
        entries: list[tuple[str, int, bool]],
        notified_at_ts: int,
    ) -> None:
        if not entries:
            return
        codes = [entry[0] for entry in entries]
        result = await session.execute(select(cls).where(col(cls.code).in_(codes)))
        existing = {row.code: row for row in result.scalars().all()}
        for code, expires_at_ts, is_permanent in entries:
            if code in existing:
                record = existing[code]
                record.expires_at_ts = expires_at_ts
                record.is_permanent = is_permanent
                record.expiring_notified_at_ts = notified_at_ts
            else:
                session.add(
                    cls(
                        code=code,
                        expires_at_ts=expires_at_ts,
                        is_permanent=is_permanent,
                        new_notified_at_ts=0,
                        expiring_notified_at_ts=notified_at_ts,
                    )
                )

    @classmethod
    @with_session
    async def prune_expired(
        cls: type[T_CalabiyauCdkeyRemind],
        session: AsyncSession,
        cutoff_ts: int,
    ) -> None:
        await session.execute(
            delete(cls).where(
                col(cls.is_permanent).is_(False),
                col(cls.expires_at_ts) < cutoff_ts,
            )
        )
