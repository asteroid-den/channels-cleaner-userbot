from datetime import datetime

from sqlalchemy import delete, func
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from channels_cleaner.database.models import Account, ApplyJob, Channel, ChannelDecision, Setting
from channels_cleaner.telegram.types import TgUser


class AccountDAO:
    session: AsyncSession

    async def upsert_account(self, user: TgUser, device_profile: str | None, now: datetime) -> None:
        statement = insert(Account).values(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            device_profile=device_profile,
            created_at=now,
            last_login_at=now,
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
            },
        )

        await self.session.execute(statement)

    async def wipe_account(self, account_id: int) -> None:
        for model in (Channel, ChannelDecision, ApplyJob, Setting):
            statement = delete(model).where(model.account_id == account_id)

            await self.session.execute(statement)

        statement = delete(Account).where(Account.id == account_id)

        await self.session.execute(statement)
