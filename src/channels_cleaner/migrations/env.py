from logging.config import fileConfig
from typing import Any, Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import create_engine, pool

from channels_cleaner.config import Settings
from channels_cleaner.database.models import Base
from channels_cleaner.database.types import UtcDateTime

config = context.config

# Only from the alembic CLI: started by the app, the migrations log through the app's own logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def render_item(type_: str, obj: Any, autogen_context: AutogenContext) -> str | Literal[False]:  # noqa: ANN401, ARG001
    # Migrations must not import app code that later changes: UtcDateTime is written down as the column type it stores
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.Text()"

    return False


def url() -> str:
    # The app passes the database it opens; the CLI works on the one Settings point to (./data in a checkout)
    return config.get_main_option("sqlalchemy.url") or f"sqlite:///{Settings().db_path}"


def run_migrations_offline() -> None:
    context.configure(
        url=url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(url(), poolclass=pool.NullPool)

    with engine.connect() as connection:
        # Batch mode: SQLite alters most things only by copying the table, which batch operations do
        context.configure(
            connection=connection, target_metadata=target_metadata, render_item=render_item, render_as_batch=True
        )

        with context.begin_transaction():
            context.run_migrations()

    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()

else:
    run_migrations_online()
