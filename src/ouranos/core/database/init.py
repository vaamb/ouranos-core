from logging import Logger
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.core.config import ConfigDict, get_db_dir
from ouranos.core.database.models.app import User
from ouranos.core.utils import humanize_list


def ensure_db_dir(config: ConfigDict):
    create_db_dir = False
    uri = config["SQLALCHEMY_DATABASE_URI"]
    uri_str = uri if not isinstance(uri, Path) else uri.name
    if "sqlite" in uri_str:
        create_db_dir = True
    else:
        for uri in config["SQLALCHEMY_BINDS"].values():
            uri_str = uri if not isinstance(uri, Path) else uri.name
            if "sqlite" in uri_str:
                create_db_dir = True
                break
    if create_db_dir:
        get_db_dir()  # Will create the dir as a side effect


async def create_db_tables(db: AsyncSQLAlchemyWrapper, config: ConfigDict) -> None:
    ensure_db_dir(config)
    await db.create_all()


async def insert_default_data(db: AsyncSQLAlchemyWrapper) -> None:
    from ouranos.core.database.models import app

    async with db.scoped_session() as session:
        await app.CommunicationChannel.insert_channels(session)
        await app.Role.insert_roles(session)
        await app.Service.insert_services(session)
        await app.Service.update_config_service_status(session)
        await app.User.insert_gaia(session)


async def check_db_revision(db: AsyncSQLAlchemyWrapper) -> None:
    from alembic.script import ScriptDirectory

    project_root = Path(__file__).parents[4]
    migration_dir = project_root / "migrations"
    script = ScriptDirectory(migration_dir)
    head = script.get_current_head()
    if head is None:
        raise Exception("No head revision found")

    not_initialized: list[str] = []
    not_up_to_date: list[str] = []
    db_binds = db.get_binds_list()
    for bind in db_binds:
        # Transient tables are generated when starting an instance and so don't need revision
        if bind == "transient":
            continue
        engine = db.get_engine_for_bind(bind)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(text("SELECT * FROM alembic_version"))
                revision = result.scalar_one_or_none()
        except DBAPIError:
            # Missing database file or `alembic_version` table
            not_initialized.append(bind or "ecosystem")
        else:
            if revision != head:
                not_up_to_date.append(bind or "ecosystem")
    if not_initialized:
        raise Exception(
            f"The database has no revision for the following bind(s): "
            f"{humanize_list(not_initialized)}. If this is a new install, run "
            f"`python -m ouranos fill-db --no-check-revision` then "
            f"`alembic stamp head`."
        )
    if not_up_to_date:
        raise Exception(
            f"The database is not up to date for the following bind(s): "
            f"{humanize_list(not_up_to_date)}."
        )


async def setup_db(
        db: AsyncSQLAlchemyWrapper,
        config: ConfigDict,
        logger: Logger,
        check_revision: bool = True,
) -> None:
    """Set up the database.

    Initialize the database with the config and create the binds mapping, create
    the database tables, and insert initial data. Check the database revision so
    the deployed DB tables remain in sync with their SQLAlchemy model.
    """
    logger.info("Setting up the database")

    # Import the models so they're included on the session factory when calling
    # `db.init()`
    from ouranos.core.database.models import app  # noqa
    from ouranos.core.database.models import archives  # noqa
    from ouranos.core.database.models import gaia  # noqa
    from ouranos.core.database.models import system  # noqa
    from ouranos.core.database.models import logging  # noqa

    # Initialize the DB and create the bindings
    db.init(config)  # ty: ignore[invalid-argument-type]  # TypedDict vs dict

    if not config["TESTING"] and check_revision:  # Revisions aren't used in tests (yet ?)
        await check_db_revision(db)

    await create_db_tables(db, config)
    await insert_default_data(db)
    logger.debug("Database set up")


async def teardown_db(db: AsyncSQLAlchemyWrapper) -> None:
    for engine in db.engines.values():
        await engine.dispose()


async def print_registration_token(db: AsyncSQLAlchemyWrapper) -> None:
    async with db.scoped_session() as session:
        token = await User.create_invitation_token(session)
        print(f"registration token: {token}")
