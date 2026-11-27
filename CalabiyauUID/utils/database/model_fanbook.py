"""Fanbook 登录账号凭证表与读写逻辑。"""

import time
from typing import TypeVar

from sqlmodel import Field, col, select
from sqlalchemy import UniqueConstraint, func, delete, select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.webconsole.mount_app import PageSchema, GsAdminModel, site
from gsuid_core.utils.database.base_models import BaseBotIDModel, with_session, with_read_session

T_CalabiyauFanbookUser = TypeVar("T_CalabiyauFanbookUser", bound="CalabiyauFanbookUser")


class CalabiyauFanbookUser(BaseBotIDModel, table=True):
    """同一平台会话对应的 Fanbook 登录凭据。"""

    __table_args__ = (
        UniqueConstraint("bot_id", "user_id", name="uq_calabiyaufanbookuser_bot_user"),
        {"extend_existing": True},
    )

    user_id: str = Field(default="", index=True, title="用户ID")
    fb_user_id: str = Field(default="", index=True, title="Fanbook用户ID")
    fb_short_id: str = Field(default="", title="Fanbook短ID")
    nickname: str = Field(default="", title="Fanbook昵称")
    avatar: str = Field(default="", title="Fanbook头像")
    sign: str = Field(default="", title="Fanbook登录令牌")
    device_id: str = Field(default="", title="设备ID")
    expire_at_ts: int = Field(default=0, title="令牌过期时间戳")
    updated_at_ts: int = Field(default=0, title="最后更新时间戳")

    @classmethod
    @with_read_session
    async def count_all(
        cls: type[T_CalabiyauFanbookUser],
        session: AsyncSession,
    ) -> int:
        result = await session.execute(sa_select(func.count()).select_from(cls))
        return int(result.scalar_one())

    @classmethod
    @with_read_session
    async def get_account(
        cls: type[T_CalabiyauFanbookUser],
        session: AsyncSession,
        bot_id: str,
        user_id: str,
    ) -> T_CalabiyauFanbookUser | None:
        result = await session.execute(
            select(cls).where(
                col(cls.bot_id) == bot_id,
                col(cls.user_id) == user_id,
            )
        )
        return result.scalars().first()

    @classmethod
    @with_read_session
    async def list_accounts(
        cls: type[T_CalabiyauFanbookUser],
        session: AsyncSession,
    ) -> list[T_CalabiyauFanbookUser]:
        result = await session.execute(select(cls).order_by(col(cls.id).asc()))
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def upsert_account(
        cls: type[T_CalabiyauFanbookUser],
        session: AsyncSession,
        *,
        bot_id: str,
        user_id: str,
        fb_user_id: str,
        fb_short_id: str,
        nickname: str,
        avatar: str,
        sign: str,
        device_id: str,
        expire_at_ts: int,
    ) -> T_CalabiyauFanbookUser:
        now_ts = int(time.time())
        result = await session.execute(
            select(cls).where(
                col(cls.bot_id) == bot_id,
                col(cls.user_id) == user_id,
            )
        )
        existing = result.scalars().first()
        if existing is not None:
            existing.fb_user_id = fb_user_id
            existing.fb_short_id = fb_short_id
            existing.nickname = nickname
            existing.avatar = avatar
            existing.sign = sign
            existing.device_id = device_id
            existing.expire_at_ts = expire_at_ts
            existing.updated_at_ts = now_ts
            return existing

        record = cls(
            bot_id=bot_id,
            user_id=user_id,
            fb_user_id=fb_user_id,
            fb_short_id=fb_short_id,
            nickname=nickname,
            avatar=avatar,
            sign=sign,
            device_id=device_id,
            expire_at_ts=expire_at_ts,
            updated_at_ts=now_ts,
        )
        session.add(record)
        return record

    @classmethod
    @with_session
    async def delete_account(
        cls: type[T_CalabiyauFanbookUser],
        session: AsyncSession,
        bot_id: str,
        user_id: str,
    ) -> bool:
        result = await session.execute(
            select(cls).where(
                col(cls.bot_id) == bot_id,
                col(cls.user_id) == user_id,
            )
        )
        target = result.scalars().first()
        if target is None:
            return False
        await session.execute(
            delete(cls).where(
                col(cls.bot_id) == bot_id,
                col(cls.user_id) == user_id,
            )
        )
        return True

    @classmethod
    @with_session
    async def update_sign(
        cls: type[T_CalabiyauFanbookUser],
        session: AsyncSession,
        *,
        bot_id: str,
        user_id: str,
        sign: str,
        expire_at_ts: int,
    ) -> bool:
        result = await session.execute(
            select(cls).where(
                col(cls.bot_id) == bot_id,
                col(cls.user_id) == user_id,
            )
        )
        target = result.scalars().first()
        if target is None:
            return False
        target.sign = sign
        target.expire_at_ts = expire_at_ts
        target.updated_at_ts = int(time.time())
        return True


@site.register_admin
class CalabiyauFanbookUserAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(label="卡拉彼丘Fanbook账号", icon="fa fa-key")
    model = CalabiyauFanbookUser
