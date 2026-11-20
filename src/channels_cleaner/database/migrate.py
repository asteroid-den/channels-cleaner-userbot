"""Schema migrations with Alembic, run on every start: the app is installed and upgraded by users, not deployed."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from channels_cleaner.database import legacy

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

    # A database from before Alembic: its rows move into the tables of the first revision before any later one runs
    if legacy.set_aside(path):
        command.upgrade(config, BASELINE_REVISION)
        legacy.move_rows(path)

    command.upgrade(config, "head")
