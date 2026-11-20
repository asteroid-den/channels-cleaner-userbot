from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from channels_cleaner.database.models import Setting


class SettingDAO:
    session: AsyncSession

    async def get_setting(self, account_id: int, key: str) -> Any:  # noqa: ANN401 - whatever JSON was stored
        statement = select(Setting.value).where(Setting.account_id == account_id, Setting.key == key)

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def set_setting(self, account_id: int, key: str, value: object) -> None:
        statement = insert(Setting).values(account_id=account_id, key=key, value=value)
        statement = statement.on_conflict_do_update(
            index_elements=[Setting.account_id, Setting.key],
            set_={"value": statement.excluded.value},
        )

        await self.session.execute(statement)
