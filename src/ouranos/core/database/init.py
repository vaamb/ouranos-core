from logging import getLogger, Logger

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import text

from ouranos import db, current_app
from ouranos.core.config import get_db_dir
from ouranos.core.database.models.app import User
from ouranos.core.utils import humanize_list


logger: Logger = getLogger("ouranos")


async def create_db_tables():
    create_db_dir = False
    if "sqlite" in current_app.config["SQLALCHEMY_DATABASE_URI"]:
        create_db_dir = True
    for uri in current_app.config["SQLALCHEMY_BINDS"].values():
        if "sqlite" in uri:
            create_db_dir = True
            break
    if create_db_dir:
        get_db_dir()

    # Import the models so they are registered
    from ouranos.core.database.models import app  # noqa
    from ouranos.core.database.models import archives  # noqa
    from ouranos.core.database.models import gaia  # noqa
    from ouranos.core.database.models import system  # noqa

    try:
        await db.create_all()
    except Exception as e:
        logger.error(
            f"An error occurred while creating models."
            f"Error msg: `{e.__class__.__name__}: {e}`"
        )
        raise e


async def insert_default_data():
    from ouranos.core.database.models import app

    async with db.scoped_session() as session:
        try:
            await app.CommunicationChannel.insert_channels(session)
            await app.Role.insert_roles(session)
            await app.Service.insert_services(session)
            await app.Service.update_email_service_status(session)
            await app.User.insert_gaia(session)
        except Exception as e:
            logger.error(
                f"An error occurred while creating base data."
                f"Error msg: `{e.__class__.__name__}: {e}`"
            )
            raise e


async def _check_db_revision_impl() -> None:
    alembic_cfg = AlembicConfig("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    head = script.get_current_head()
    if head is None:
        raise Exception("No head revision found")

    not_up_to_date: list[str] = []
    db_binds = db.get_binds_list()
    for bind in db_binds:
        engine = db.get_engine_for_bind(bind)
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT * FROM alembic_version"))
            revision = result.scalar_one_or_none()
        if revision != head:
            not_up_to_date.append(bind or "ecosystem")
    if not_up_to_date:
        raise Exception(
            f"The database is not up to date for the following bind(s): "
            f"{humanize_list(not_up_to_date)}."
        )


async def check_db_revision() -> None:
    try:
        await _check_db_revision_impl()
    except Exception as e:
        logger.error(
            f"An error occurred while checking the database revision."
            f"Error msg: {e}"
        )
        raise e


async def print_registration_token():
    async with db.scoped_session() as session:
        try:
            token = await User.create_invitation_token(session)
            print(f"registration token: {token}")
        except Exception as e:
            logger.error(
                f"An error occurred while generating the invitation token."
                f"Error msg: `{e.__class__.__name__}: {e}`"
            )
            raise e
