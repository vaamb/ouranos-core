import asyncio
import logging
from logging.config import fileConfig
import typing as t

from sqlalchemy import MetaData
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

import ouranos
from ouranos import db
from ouranos.core.config import get_db_dir


if t.TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine
    from sqlalchemy.ext.asyncio import AsyncConnection


USE_TWOPHASE = False

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")

# gather section names referring to different
# databases.  These are named "engine1", "engine2"
# in the sample .ini file.
db_names = config.get_main_option("databases", "")

# add your model's MetaData objects here
# for 'autogenerate' support.  These must be set
# up to hold just those tables targeting a
# particular database. table.tometadata() may be
# helpful here in case a "copy" of
# a MetaData is needed.
# from myapp import mymodel
# target_metadata = {
#       'engine1':mymodel.metadata1,
#       'engine2':mymodel.metadata2
# }

ouranos_cfg = ouranos.setup_config()
db.init(ouranos_cfg)

# Patch config
base_bind = "ecosystems"
binds_keys = [base_bind, *db.config.binds.keys()]
index = binds_keys.index("memory")
del binds_keys[index]

config.set_main_option("databases", ",".join(binds_keys))

create_db_dir = False
for name in binds_keys:
    if name == base_bind:
        bind_key = None
    else:
        bind_key = name
    uri = db.get_uri_for_bind(bind_key)  # Will print a warning for "ecosystems" which is the default DB
    if "sqlite" in uri:
        create_db_dir = True
    config.set_section_option(name, "sqlalchemy.url", uri)

if create_db_dir:
    get_db_dir()

# Create the metadata dict
target_metadata = {
    binds_key: MetaData()
    for binds_key in binds_keys
}
for name in binds_keys:
    if name == base_bind:
        bind_key = None
    else:
        bind_key = name
    tables = db.get_tables_for_bind(bind_key)
    for table in tables:
        table.to_metadata(target_metadata[name])


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    # for the --sql use case, run migrations for each URL into
    # individual files.

    engines = {}
    for name in binds_keys:
        engines[name] = rec = {}
        rec["url"] = context.config.get_section_option(name, "sqlalchemy.url")

    for name, rec in engines.items():
        logger.info("Migrating database %s" % name)
        file_ = "%s.sql" % name
        logger.info("Writing output to %s" % file_)
        with open(file_, "w") as buffer:
            context.configure(
                url=rec["url"],
                output_buffer=buffer,
                target_metadata=target_metadata.get(name),
                literal_binds=True,
                dialect_opts={"paramstyle": "named"},
            )
            with context.begin_transaction():
                context.run_migrations(engine_name=name)


def do_run_migrations(connection: Connection, engines: dict) -> None:
    # for the direct-to-DB use case, start a transaction on all
    # engines, then run all migrations, then commit all transactions.

    for name, rec in engines.items():
        async_conn: AsyncConnection = rec["connection"]
        rec['sync_connection'] = conn = async_conn.sync_connection
        if USE_TWOPHASE:
            rec["transaction"] = conn.begin_twophase()
        else:
            rec["transaction"] = conn.begin()

    try:
        for name, rec in engines.items():
            logger.info("Migrating database %s" % name)
            context.configure(
                connection=rec['sync_connection'],
                upgrade_token="%s_upgrades" % name,
                downgrade_token="%s_downgrades" % name,
                target_metadata=target_metadata.get(name),
            )
            context.run_migrations(engine_name=name)

        if USE_TWOPHASE:
            for rec in engines.values():
                rec["transaction"].prepare()

        for rec in engines.values():
            rec["transaction"].commit()
    except:  # noqa: E722
        for rec in engines.values():
            rec["transaction"].rollback()
        raise
    finally:
        for rec in engines.values():
            rec["sync_connection"].close()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    engines = {}
    for name in binds_keys:
        engines[name] = rec = {}
        rec["engine"]: AsyncEngine = async_engine_from_config(
            context.config.get_section(name, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    for name, rec in engines.items():
        engine: AsyncEngine = rec["engine"]
        rec["connection"] = conn = engine.connect()
        await conn.start()

    # Run migration inside a greenlet spawn
    await engines[base_bind]["connection"].run_sync(do_run_migrations, engines)

    for rec in engines.values():
        await rec["connection"].close()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
