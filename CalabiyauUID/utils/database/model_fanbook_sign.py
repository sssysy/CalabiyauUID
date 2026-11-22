"""Fanbook 自动签到配置与每日签到状态表。"""

import time
from typing import TypeVar

from sqlmodel import Field, col, select
from sqlalchemy import UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.webconsole.mount_app import PageSchema, GsAdminModel, site
from gsuid_core.utils.database.base_models import BaseBotIDModel, with_session, with_read_session

T_CalabiyauFanbookSign = TypeVar("T_CalabiyauFanbookSign", bound="CalabiyauFanbookSign")


class CalabiyauFanbookSign(BaseBotIDModel, table=True):
    """记录每个会话用户的 Fanbook 自动签到开关及今日签到结果。"""

    __table_args__ = (
        UniqueConstraint("bot_id", "user_id", name="uq_calabiyaufanbooksign_bot_user"),
        {"extend_existing": True},
    )

    user_id: str = Field(default="", index=True, title="用户ID")
    auto_sign: bool = Field(default=False, title="开启自动签到")
    last_sign_date: str = Field(default="", index=True, title="最近签到日期")
    last_status: str = Field(default="", title="最近签到状态")
    last_msg: str = Field(default="", title="最近签到摘要")
    total_days: int = Field(default=0, title="累计签到天数")
    continuous_days: int = Field(default=0, title="连续签到天数")
    shop_point: int = Field(default=0, title="当前积分")
    updated_at_ts: int = Field(default=0, title="最后更新时间戳")

    @classmethod
    @with_read_session
    async def get_record(
        cls: type[T_CalabiyauFanbookSign],
        session: AsyncSession,
        bot_id: str,
        user_id: str,
    ) -> T_CalabiyauFanbookSign | None:
        result = await session.execute(
            select(cls).where(
                col(cls.bot_id) == bot_id,
                col(cls.user_id) == user_id,
            )
        )
        return result.scalars().first()

    @classmethod
    @with_read_session
    async def list_auto_sign_keys(
        cls: type[T_CalabiyauFanbookSign],
        session: AsyncSession,
    ) -> set[tuple[str, str]]:
        result = await session.execute(select(cls).where(col(cls.auto_sign).is_(True)))
        return {(row.bot_id, row.user_id) for row in result.scalars().all()}

    @classmethod
    @with_read_session
    async def list_signed_today_keys(
        cls: type[T_CalabiyauFanbookSign],
        session: AsyncSession,
        sign_date: str,
    ) -> set[tuple[str, str]]:
        result = await session.execute(
            select(cls).where(
                col(cls.last_sign_date) == sign_date,
                col(cls.last_status) == "ok",
            )
        )
        return {(row.bot_id, row.user_id) for row in result.scalars().all()}

    @classmethod
    @with_session
    async def set_auto_sign(
        cls: type[T_CalabiyauFanbookSign],
        session: AsyncSession,
        bot_id: str,
        user_id: str,
        *,
        enabled: bool,
    ) -> bool:
        result = await session.execute(
            select(cls).where(
                col(cls.bot_id) == bot_id,
                col(cls.user_id) == user_id,
            )
        )
        existing = result.scalars().first()
        now_ts = int(time.time())
        if existing is not None:
            changed = existing.auto_sign != enabled
            existing.auto_sign = enabled
            existing.updated_at_ts = now_ts
            return changed

        if not enabled:
            return False
        session.add(
            cls(
                bot_id=bot_id,
                user_id=user_id,
                auto_sign=True,
                updated_at_ts=now_ts,
            )
        )
        return True

    @classmethod
    @with_session
    async def record_outcome(
        cls: type[T_CalabiyauFanbookSign],
        session: AsyncSession,
        *,
        bot_id: str,
        user_id: str,
        sign_date: str,
        status: str,
        msg: str,
        total_days: int = 0,
        continuous_days: int = 0,
        shop_point: int = 0,
    ) -> None:
        result = await session.execute(
            select(cls).where(
                col(cls.bot_id) == bot_id,
                col(cls.user_id) == user_id,
            )
        )
        existing = result.scalars().first()
        now_ts = int(time.time())
        if existing is not None:
            existing.last_sign_date = sign_date
            existing.last_status = status
            existing.last_msg = msg
            if total_days > 0:
                existing.total_days = total_days
            if continuous_days > 0:
                existing.continuous_days = continuous_days
            if shop_point > 0:
                existing.shop_point = shop_point
            existing.updated_at_ts = now_ts
            return

        session.add(
            cls(
                bot_id=bot_id,
                user_id=user_id,
                auto_sign=False,
                last_sign_date=sign_date,
                last_status=status,
                last_msg=msg,
                total_days=total_days,
                continuous_days=continuous_days,
                shop_point=shop_point,
                updated_at_ts=now_ts,
            )
        )


@site.register_admin
class CalabiyauFanbookSignAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(label="卡拉彼丘Fanbook签到", icon="fa fa-calendar-check-o")
    model = CalabiyauFanbookSign
