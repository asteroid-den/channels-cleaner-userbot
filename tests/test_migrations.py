from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import Dialect
from sqlalchemy.dialects import sqlite

from channels_cleaner.database import DAO, DatabaseManager, legacy, migrate
from channels_cleaner.database.types import UtcDateTime
from channels_cleaner.enums import ChatKind, ChatRole, Decision, DecisionStatus

_DIALECT: Dialect = sqlite.dialect()


def _tables(path: Path) -> set[str]:
    with closing(sqlite3.connect(path)) as connection:
        return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_fresh_database_matches_the_models(tmp_path: Path) -> None:
    path = tmp_path / "fresh.sqlite3"
    migrate.upgrade(path)

    # Raises when the models and the migrated schema differ
    command.check(migrate.alembic_config(path))


def test_migrations_go_down_and_up_again(tmp_path: Path) -> None:
    path = tmp_path / "fresh.sqlite3"
    config = migrate.alembic_config(path)
    migrate.upgrade(path)

    command.downgrade(config, "base")
    # sqlite_sequence is SQLite's own, left by the AUTOINCREMENT table
    assert _tables(path) - {"sqlite_sequence"} == {"alembic_version"}

    command.upgrade(config, "head")
    command.check(config)


def _legacy_database(path: Path, steps: int) -> None:
    """A database as a version before Alembic left it, after ``steps`` of its migrations."""
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("CREATE TABLE schema_version (version INTEGER)")

        for version, script in enumerate(legacy.LEGACY_MIGRATIONS[:steps], start=1):
            connection.executescript(script)
            connection.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

        connection.execute(
            "INSERT INTO channels (account_id, channel_id, title, unread_count, is_muted, is_archived,"
            " last_post_at, synced_at, gone) VALUES (1, -1001, 'Old News', 7, 1, 0,"
            " '2026-11-01T10:00:00.123456+00:00', '2026-11-17T20:00:00+00:00', 0)"
        )
        connection.execute(
            "INSERT INTO decisions (account_id, channel_id, decision, status, decided_at, applied_at)"
            " VALUES (1, -1001, 'mute', 'applied', '2026-11-17T20:01:00+00:00', '2026-11-17T20:05:00+00:00')"
        )
        connection.execute(
            "INSERT INTO settings (account_id, key, value) VALUES (1, 'deck_prefs', '{\"sort\": \"dead\"}')"
        )


@pytest.mark.parametrize("steps", [1, len(legacy.LEGACY_MIGRATIONS)])
def test_database_from_before_alembic_is_taken_over(tmp_path: Path, steps: int) -> None:
    path = tmp_path / "cleaner.sqlite3"
    _legacy_database(path, steps)

    migrate.upgrade(path)

    assert "schema_version" not in _tables(path)
    command.check(migrate.alembic_config(path))

    async def read() -> None:
        manager = DatabaseManager(path)

        async with manager.session() as session:
            dao = DAO(session)
            channel = await dao.get_channel(1, -1001)
            assert channel is not None
            assert channel.last_post_at == datetime(2026, 11, 1, 10, 0, 0, 123456, tzinfo=UTC)
            assert (channel.is_muted, channel.is_archived, channel.unread_count) == (True, False, 7)
            # Columns added by the legacy steps after the first one get their defaults
            assert (channel.kind, channel.role) == (ChatKind.CHANNEL, ChatRole.MEMBER)
            assert channel.decision is not None
            assert (channel.decision.decision, channel.decision.status) == (Decision.MUTE, DecisionStatus.APPLIED)
            assert await dao.get_setting(1, "deck_prefs") == {"sort": "dead"}

        await manager.dispose()

    asyncio.run(read())


def test_a_takeover_cut_short_is_finished(tmp_path: Path) -> None:
    path = tmp_path / "cleaner.sqlite3"
    _legacy_database(path, len(legacy.LEGACY_MIGRATIONS))
    # Tables set aside, then the app stopped before Alembic created the new ones
    assert legacy.set_aside(path)

    migrate.upgrade(path)

    assert not {table for table in _tables(path) if table.startswith("legacy_")}
    command.check(migrate.alembic_config(path))

    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT title FROM channels").fetchall() == [("Old News",)]


def test_utc_datetime_keeps_the_stored_format() -> None:
    column = UtcDateTime()
    moscow = timezone(timedelta(hours=3))

    stored = column.process_bind_param(datetime(2026, 11, 17, 23, 0, tzinfo=moscow), _DIALECT)

    assert stored == "2026-11-17T20:00:00+00:00"
    assert column.process_result_value(stored, _DIALECT) == datetime(2026, 11, 17, 20, 0, tzinfo=UTC)


def test_utc_datetime_refuses_naive_values() -> None:
    with pytest.raises(ValueError, match="Naive datetime"):
        UtcDateTime().process_bind_param(datetime(2026, 11, 17, 20, 0), _DIALECT)  # noqa: DTZ001


async def test_concurrent_writers_wait_for_each_other(tmp_path: Path) -> None:
    path = tmp_path / "cleaner.sqlite3"
    migrate.upgrade(path)
    manager = DatabaseManager(path)

    async def write(n: int) -> None:
        async with manager.session() as session:
            dao = DAO(session)
            await dao.set_setting(1, f"key-{n}", n)
            await dao.commit()

    # The sync, the apply job and the API each write in their own session
    await asyncio.gather(*(write(n) for n in range(30)))

    async with manager.session() as session:
        assert [await DAO(session).get_setting(1, f"key-{n}") for n in range(30)] == list(range(30))

    await manager.dispose()


def test_a_legacy_step_that_fails_leaves_nothing_behind(tmp_path: Path) -> None:
    path = tmp_path / "cleaner.sqlite3"
    _legacy_database(path, 1)

    with closing(sqlite3.connect(path, isolation_level=None)) as connection:
        with pytest.raises(sqlite3.OperationalError):
            legacy._transaction(  # noqa: SLF001
                connection,
                ["ALTER TABLE channels ADD COLUMN pulse TEXT", "INSERT INTO no_such_table VALUES (1)"],
            )

        columns = {row[1] for row in connection.execute("PRAGMA table_info(channels)")}

    # Rolled back as a whole: the next start adds the column again instead of tripping over it
    assert "pulse" not in columns
    migrate.upgrade(path)
    command.check(migrate.alembic_config(path))


def test_a_database_is_backed_up_before_it_is_migrated(tmp_path: Path) -> None:
    path = tmp_path / "cleaner.sqlite3"
    _legacy_database(path, len(legacy.LEGACY_MIGRATIONS))

    migrate.upgrade(path)

    backups = list(tmp_path.glob("cleaner.sqlite3.before-*"))
    assert len(backups) == 1
    assert "schema_version" in _tables(backups[0])

    # Up to date: nothing to change, nothing to copy
    backups[0].unlink()
    migrate.upgrade(path)
    assert not list(tmp_path.glob("cleaner.sqlite3.before-*"))


def test_a_new_database_needs_no_backup(tmp_path: Path) -> None:
    migrate.upgrade(tmp_path / "fresh.sqlite3")

    assert not list(tmp_path.glob("*.before-*"))
