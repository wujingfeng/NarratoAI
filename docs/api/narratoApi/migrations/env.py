from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from narrato_api.database import Base
from narrato_api.auth import models as _auth_models
from narrato_api.billing import models as _billing_models
from narrato_api.projects import models as _project_models
from narrato_api.assets import models as _asset_models
from narrato_api.workflows import models as _workflow_models

assert _auth_models.User.__tablename__ == "users"
assert _billing_models.CreditAccount.__tablename__ == "credit_accounts"
assert _project_models.Project.__tablename__ == "projects"
assert _asset_models.Asset.__tablename__ == "assets"
assert _workflow_models.Workflow.__tablename__ == "workflows"

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

if database_url := os.getenv("NARRATO_API_DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """在不连接数据库时生成业务库迁移 SQL。"""

    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """连接独立业务数据库并执行迁移。"""

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
