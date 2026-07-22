import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.database import Base

# 确保所有模型已注册到 Base.metadata
import app.models  # noqa: F401

config = context.config

# Alembic uses a sync engine (pymysql), never aiomysql.
# Read the app's DATABASE_URL and swap the driver.
_raw_url = os.environ.get("DATABASE_URL", "")
if _raw_url:
    db_url = _raw_url.replace("mysql+aiomysql://", "mysql+pymysql://")
else:
    from app.core.config import settings
    db_url = settings.DATABASE_URL.replace("mysql+aiomysql", "mysql+pymysql")

config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
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
