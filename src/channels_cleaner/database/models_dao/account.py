from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from channels_cleaner.database.models import Account, ApplyJob, Channel, ChannelDecision, Setting
from channels_cleaner.telegram.types import TgUser


class AccountDAO:
    session: AsyncSession

    async def upsert_account(self, user: TgUser, device_profile: str | None, session_name: str, now: datetime) -> None:
        # A session file belongs to one account: one logged out earlier may have had this name
        statement = (
            update(Account).where(Account.session_name == session_name, Account.id != user.id).values(session_name=None)
        )

        await self.session.execute(statement)

        statement = insert(Account).values(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            device_profile=device_profile,
            created_at=now,
            last_login_at=now,
            session_name=session_name,
            selected_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[Account.id],
            set_={
                "first_name": statement.excluded.first_name,
                "last_name": statement.excluded.last_name,
                "username": statement.excluded.username,
                # A login without a profile (mock mode) keeps the one the session already presents
                "device_profile": func.coalesce(statement.excluded.device_profile, Account.device_profile),
                "last_login_at": statement.excluded.last_login_at,
                "session_name": statement.excluded.session_name,
                "selected_at": statement.excluded.selected_at,
            },
        )

        await self.session.execute(statement)

    async def get_account(self, account_id: int) -> Account | None:
        statement = select(Account).where(Account.id == account_id).execution_options(populate_existing=True)

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_accounts(self) -> list[Account]:
        """Accounts with a session to switch to, in the order they were added."""
        statement = (
            select(Account)
            .where(Account.session_name.is_not(None))
            .order_by(Account.created_at, Account.id)
            .execution_options(populate_existing=True)
        )

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def active_session(self) -> str | None:
        statement = (
            select(Account.session_name)
            .where(Account.session_name.is_not(None))
            .order_by(Account.selected_at.desc().nulls_last(), Account.last_login_at.desc())
            .limit(1)
        )

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def select_account(self, account_id: int, now: datetime) -> None:
        statement = update(Account).where(Account.id == account_id).values(selected_at=now)

        await self.session.execute(statement)

    async def forget_session(self, account_id: int) -> None:
        statement = update(Account).where(Account.id == account_id).values(session_name=None)

        await self.session.execute(statement)

    async def wipe_account(self, account_id: int) -> None:
        for model in (Channel, ChannelDecision, ApplyJob, Setting):
            statement = delete(model).where(model.account_id == account_id)

            await self.session.execute(statement)

        statement = delete(Account).where(Account.id == account_id)

        await self.session.execute(statement)
