import logging
import sqlite3
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from channels_cleaner import __version__
from channels_cleaner.database import legacy

log = logging.getLogger(__name__)

SCRIPT_LOCATION = "channels_cleaner:migrations"
#: the revision that creates the schema of the last legacy step (database/legacy.py)
BASELINE_REVISION = "685f08492209"


def alembic_config(path: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return config


def upgrade(path: Path) -> None:
    config = alembic_config(path)
    backup(path, config)

    # A database from before Alembic: its rows move into the tables of the first revision before any later one runs
    if legacy.set_aside(path):
        command.upgrade(config, BASELINE_REVISION)
        legacy.move_rows(path)

    command.upgrade(config, "head")


def backup(path: Path, config: Config) -> Path | None:
    """Copies the database before migrating it, once per app version: it holds the user's decisions and history."""
    if not path.exists():
        return None

    with closing(sqlite3.connect(path)) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        revision = (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()
            if "alembic_version" in tables
            else None
        )

    if not tables - {"sqlite_sequence", "alembic_version"}:
        return None

    head = ScriptDirectory.from_config(config).get_current_head()

    if revision is not None and revision[0] == head and not any(table.startswith("legacy_") for table in tables):
        return None

    target = path.with_name(f"{path.name}.before-{__version__}")

    if not target.exists():
        # The backup API copies a consistent snapshot, the WAL included
        with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(target)) as copy:
            source.backup(copy)

        log.info("Backed up %s to %s before migrating it", path, target)

    return target
