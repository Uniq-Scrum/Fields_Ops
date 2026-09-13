"""
Alembic migration environment.

The database URL is never read from alembic.ini (which would mean either
hardcoding it or duplicating .env parsing) — it comes from the same
`Settings` object (`app.core.config.settings`) the running application
uses, so migrations always target whatever POSTGRES_* the current
environment/.env resolves to.

`target_metadata` is `Base.metadata` from `app.core.database`; every ORM
model module must be imported below (even if only for its side effect of
registering with `Base.metadata`) for `alembic revision --autogenerate` to
see it.
"""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from app.core.config import settings
from app.core.database import Base

# Import every model module so Base.metadata is fully populated before
# autogenerate compares it against the live database schema.
import app.models.user  # noqa: F401
import app.models.field_officer  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection (`alembic upgrade --sql`)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection.

    Uses NullPool: migrations are a one-shot process, not a long-lived
    pooled connection like the application's engine in app/core/database.py.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
