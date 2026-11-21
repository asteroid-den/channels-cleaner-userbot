import asyncio
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from channels_cleaner.database import migrate

# Seconds a connection waits for another one's write lock: the sync, the apply job and the API write at the same
# time, each in short transactions
BUSY_TIMEOUT = 15


class DatabaseManager:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{path}", connect_args={"timeout": BUSY_TIMEOUT})
        self.session = async_sessionmaker(bind=self.engine, expire_on_commit=False)
        event.listen(self.engine.sync_engine, "connect", on_connect)

    async def migrate(self) -> None:
        # Alembic is synchronous and runs its own engine
        await asyncio.to_thread(migrate.upgrade, self.path)

    async def dispose(self) -> None:
        await self.engine.dispose()


def on_connect(connection: Any, _: object) -> None:  # noqa: ANN401 - a DBAPI connection
    cursor = connection.cursor()
    # Readers don't wait for the writer and the other way round
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()
