"""卡拉彼丘账号绑定表与读写逻辑。"""

from typing import TypeVar

from sqlmodel import Field, col, select
from sqlalchemy import Table, MetaData, UniqueConstraint, text, delete, select as sa_select, update, inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.server import on_core_start_before
from gsuid_core.utils.database import base_models
from gsuid_core.webconsole.mount_app import PageSchema, GsAdminModel, site
from gsuid_core.utils.database.base_models import BaseBotIDModel, with_session, with_read_session

T_CalabiyauBind = TypeVar("T_CalabiyauBind", bound="CalabiyauBind")
_LEGACY_SESSION_COLUMNS = frozenset({"bot_id", "bot_self_id", "group_id"})


class CalabiyauBind(BaseBotIDModel, table=True):
    """同一平台用户与卡拉彼丘 UID 的全局绑定。"""

    __table_args__ = (
        UniqueConstraint("bot_id", "user_id", "game_uid", name="uq_calabiyaubind_bot_user_uid"),
        {"extend_existing": True},
    )

    user_id: str = Field(default="", index=True, title="用户ID")
    game_uid: str = Field(default="", index=True, title="卡拉彼丘UID")
    is_main: bool = Field(default=False, title="是否当前账号")

    @classmethod
    @with_read_session
    async def get_binds(
        cls: type[T_CalabiyauBind],
        session: AsyncSession,
        bot_id: str,
        user_id: str,
    ) -> list[T_CalabiyauBind]:
        result = await session.execute(
            select(cls)
            .where(
                col(cls.bot_id) == bot_id,
                col(cls.user_id) == user_id,
            )
            .order_by(col(cls.id).asc())
        )
        return list(result.scalars().all())

    @classmethod
    @with_read_session
    async def get_bind(
        cls: type[T_CalabiyauBind],
        session: AsyncSession,
        bot_id: str,
        user_id: str,
        game_uid: str,
    ) -> T_CalabiyauBind | None:
        result = await session.execute(
            select(cls).where(
                col(cls.bot_id) == bot_id,
                col(cls.user_id) == user_id,
                col(cls.game_uid) == game_uid,
            )
        )
        return result.scalars().first()

    @classmethod
    @with_session
    async def add_bind(
        cls: type[T_CalabiyauBind],
        session: AsyncSession,
        bot_id: str,
        user_id: str,
        game_uid: str,
    ) -> bool:
        result = await session.execute(
            select(cls).where(
                col(cls.bot_id) == bot_id,
                col(cls.user_id) == user_id,
                col(cls.game_uid) == game_uid,
            )
        )
        if result.scalars().first() is not None:
            return False

        await session.execute(
            update(cls)
            .where(
                col(cls.bot_id) == bot_id,
                col(cls.user_id) == user_id,
                col(cls.is_main).is_(True),
            )
            .values(is_main=False)
        )
        session.add(cls(bot_id=bot_id, user_id=user_id, game_uid=game_uid, is_main=True))
        return True

    @classmethod
    @with_session
    async def delete_bind(
        cls: type[T_CalabiyauBind],
        session: AsyncSession,
        bot_id: str,
        user_id: str,
        game_uid: str,
    ) -> tuple[bool, bool, str | None]:
        result = await session.execute(
            select(cls).where(
                col(cls.bot_id) == bot_id,
                col(cls.user_id) == user_id,
                col(cls.game_uid) == game_uid,
            )
        )
        target = result.scalars().first()
        if target is None:
            return False, False, None

        was_main = target.is_main
        await session.execute(
            delete(cls).where(
                col(cls.bot_id) == bot_id,
                col(cls.user_id) == user_id,
                col(cls.game_uid) == game_uid,
            )
        )

        remaining_result = await session.execute(
            select(cls)
            .where(
                col(cls.bot_id) == bot_id,
                col(cls.user_id) == user_id,
            )
            .order_by(col(cls.id).asc())
        )
        remaining = list(remaining_result.scalars().all())
        if not remaining:
            return True, was_main, None

        current_main = next((bind for bind in remaining if bind.is_main), None)
        if current_main is None and was_main:
            current_main = remaining[0]
            await session.execute(update(cls).where(col(cls.id) == current_main.id).values(is_main=True))
        return True, was_main, current_main.game_uid if current_main is not None else None


@site.register_admin
class CalabiyauBindAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(label="卡拉彼丘绑定管理", icon="fa fa-users")
    model = CalabiyauBind


def _migrate_legacy_table(connection: Connection) -> None:
    """把旧绑定表迁移成 bot_id + user_id 绑定表。"""
    inspector = inspect(connection)
    if CalabiyauBind.__tablename__ not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns(CalabiyauBind.__tablename__)}
    if _LEGACY_SESSION_COLUMNS <= columns:
        _migrate_session_table(connection)
    elif "bot_id" not in columns:
        _migrate_user_only_table(connection)


def _migrate_session_table(connection: Connection) -> None:
    legacy = Table(CalabiyauBind.__tablename__, MetaData(), autoload_with=connection)
    rows = connection.execute(
        sa_select(
            legacy.c.bot_id,
            legacy.c.user_id,
            legacy.c.game_uid,
            legacy.c.is_main,
        ).order_by(legacy.c.id.asc())
    ).all()
    _recreate_bind_table(connection, legacy, rows)


def _migrate_user_only_table(connection: Connection) -> None:
    legacy = Table(CalabiyauBind.__tablename__, MetaData(), autoload_with=connection)
    rows = connection.execute(
        sa_select(
            legacy.c.user_id,
            legacy.c.game_uid,
            legacy.c.is_main,
        ).order_by(legacy.c.id.asc())
    ).all()
    _recreate_bind_table(connection, legacy, rows)


def _recreate_bind_table(
    connection: Connection,
    legacy: Table,
    rows: list[tuple[object, ...]],
) -> None:
    merged: dict[tuple[str, str], dict[str, bool]] = {}
    for row in rows:
        raw_bot_id = row[0] if len(row) == 4 else ""
        raw_user_id = row[1] if len(row) == 4 else row[0]
        raw_game_uid = row[2] if len(row) == 4 else row[1]
        raw_is_main = row[3] if len(row) == 4 else row[2]
        if not isinstance(raw_bot_id, str) or not isinstance(raw_user_id, str) or not isinstance(raw_game_uid, str):
            continue
        account = merged.setdefault((raw_bot_id, raw_user_id), {})
        account[raw_game_uid] = account.get(raw_game_uid, False) or raw_is_main is True

    legacy.drop(connection)
    CalabiyauBind.__table__.create(connection)
    for (bot_id, user_id), accounts in merged.items():
        if not accounts:
            continue
        main_uid = next((game_uid for game_uid, is_main in accounts.items() if is_main), next(iter(accounts)))
        connection.execute(
            text(
                "INSERT INTO calabiyaubind (bot_id, user_id, game_uid, is_main) "
                "VALUES (:bot_id, :user_id, :game_uid, :is_main)"
            ),
            {"bot_id": bot_id, "user_id": user_id, "game_uid": main_uid, "is_main": True},
        )
        for game_uid in accounts:
            if game_uid == main_uid:
                continue
            connection.execute(
                text(
                    "INSERT INTO calabiyaubind (bot_id, user_id, game_uid, is_main) "
                    "VALUES (:bot_id, :user_id, :game_uid, :is_main)"
                ),
                {"bot_id": bot_id, "user_id": user_id, "game_uid": game_uid, "is_main": False},
            )


@on_core_start_before(priority=-95)
async def migrate_calabiyau_bind_table() -> None:
    async with base_models.async_maker() as session:
        connection = await session.connection()
        await connection.run_sync(_migrate_legacy_table)
        await session.commit()
