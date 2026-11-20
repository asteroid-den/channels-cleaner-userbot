from sqlalchemy.ext.asyncio import AsyncSession

from channels_cleaner.database.models_dao import AccountDAO, ApplyJobDAO, ChannelDAO, DecisionDAO, SettingDAO


class DAO(AccountDAO, ApplyJobDAO, ChannelDAO, DecisionDAO, SettingDAO):
    """All queries of the app over one session.

    Writes are Core statements (upserts, bulk updates): they don't touch objects the session has already loaded, so
    the selects that return objects read them anew (populate_existing) instead of handing back a stale copy.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
