"""The schema migrations from before Alembic, for databases created by versions up to 1.4.

They counted up in a ``schema_version`` table. A database that has one is brought to the last of these steps and its
tables are set aside; Alembic creates them anew from the first revision, the rows move over, and from there Alembic
takes over. Copied rather than stamped: the old tables declare TEXT and INTEGER where the models have VARCHAR, BOOLEAN
and JSON. SQLite stores the same values either way, but Alembic would see a different schema in every old database.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

TABLES = ("accounts", "channels", "decisions", "apply_jobs", "settings")
_ASIDE = "legacy_"

# Never changes: the step list ended with 1.4, new schema changes are Alembic revisions
LEGACY_MIGRATIONS: list[str] = [
    # 1 — initial schema
    """
    CREATE TABLE accounts (
        id              INTEGER PRIMARY KEY,
        first_name      TEXT NOT NULL,
        last_name       TEXT,
        username        TEXT,
        device_profile  TEXT,
        created_at      TEXT NOT NULL,
        last_login_at   TEXT NOT NULL
    );
    CREATE TABLE channels (
        account_id       INTEGER NOT NULL,
        channel_id       INTEGER NOT NULL,
        title            TEXT NOT NULL,
        username         TEXT,
        about            TEXT,
        members_count    INTEGER,
        unread_count     INTEGER NOT NULL DEFAULT 0,
        is_muted         INTEGER NOT NULL DEFAULT 0,
        is_archived      INTEGER NOT NULL DEFAULT 0,
        photo_file_id    TEXT,
        photo_unique_id  TEXT,
        last_post_id     INTEGER,
        last_post_at     TEXT,
        last_post_text   TEXT,
        last_post_media  TEXT,
        full_fetched_at  TEXT,
        synced_at        TEXT NOT NULL,
        gone             INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (account_id, channel_id)
    );
    CREATE TABLE decisions (
        account_id   INTEGER NOT NULL,
        channel_id   INTEGER NOT NULL,
        decision     TEXT NOT NULL,
        status       TEXT NOT NULL,
        decided_at   TEXT NOT NULL,
        applied_at   TEXT,
        error        TEXT,
        PRIMARY KEY (account_id, channel_id)
    );
    CREATE TABLE apply_jobs (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id   INTEGER NOT NULL,
        status       TEXT NOT NULL,
        total        INTEGER NOT NULL,
        done         INTEGER NOT NULL DEFAULT 0,
        failed       INTEGER NOT NULL DEFAULT 0,
        started_at   TEXT NOT NULL,
        finished_at  TEXT
    );
    CREATE TABLE settings (
        account_id  INTEGER NOT NULL,
        key         TEXT NOT NULL,
        value       TEXT NOT NULL,
        PRIMARY KEY (account_id, key)
    );
    """,
    # 2 — weekly posting activity ("pulse"), cached as JSON alongside the full info
    """
    ALTER TABLE channels ADD COLUMN pulse TEXT;
    """,
    # 3 — an action the app already applied that a changed decision has to undo
    """
    ALTER TABLE decisions ADD COLUMN reverts TEXT;
    """,
    # 4 — channels and supergroups share the table; ids don't collide, ``kind`` tells them apart
    """
    ALTER TABLE channels ADD COLUMN kind TEXT NOT NULL DEFAULT 'channel';
    """,
    # 5 — chats the user owns or administers are listed too, marked by ``role``
    """
    ALTER TABLE channels ADD COLUMN role TEXT NOT NULL DEFAULT 'member';
    """,
]


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _transaction(connection: sqlite3.Connection, statements: list[str]) -> None:
    """Run the statements all or nothing. SQLite's DDL is transactional, but executescript commits on its own."""
    connection.execute("BEGIN")

    try:
        for statement in statements:
            connection.execute(statement)

    except BaseException:
        connection.execute("ROLLBACK")
        raise

    connection.execute("COMMIT")


def _statements(script: str) -> list[str]:
    # The legacy scripts are plain DDL: no semicolons inside strings or triggers
    return [statement.strip() for statement in script.split(";") if statement.strip()]


def set_aside(path: Path) -> bool:
    """Bring a database from before Alembic to the last legacy step and rename its tables out of the way.

    Returns whether set-aside tables are waiting for their rows to move, now or since an earlier start that stopped.
    Every step commits together with its version row, so a start cut short at any point is finished by the next one.
    """
    if not path.exists():
        return False

    # closing(): a sqlite3 connection used as a context manager commits but stays open.
    # isolation_level=None: no implicit transactions, _transaction() opens them
    with closing(sqlite3.connect(path, isolation_level=None)) as connection:
        tables = _tables(connection)

        if "schema_version" in tables:
            current = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0

            for version, script in enumerate(LEGACY_MIGRATIONS, start=1):
                if version > current:
                    # The version is enumerate()'s int
                    row = f"INSERT INTO schema_version (version) VALUES ({version})"  # noqa: S608
                    _transaction(connection, [*_statements(script), row])

            _transaction(
                connection,
                [*(f"ALTER TABLE {table} RENAME TO {_ASIDE}{table}" for table in TABLES), "DROP TABLE schema_version"],
            )
            tables = _tables(connection)

        return any(table.startswith(_ASIDE) for table in tables)


def move_rows(path: Path) -> None:
    """Move the rows of the set-aside tables into the ones Alembic created, then drop them."""
    with closing(sqlite3.connect(path)) as connection, connection:
        for table in TABLES:
            aside = f"{_ASIDE}{table}"
            old = {row[1] for row in connection.execute(f"PRAGMA table_info({aside})")}

            if not old:
                continue

            new = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
            columns = ", ".join(column for column in new if column in old)
            connection.execute(f"INSERT INTO {table} ({columns}) SELECT {columns} FROM {aside}")  # noqa: S608 - names from the schema
            connection.execute(f"DROP TABLE {aside}")
