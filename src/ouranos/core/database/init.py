from logging import getLogger, Logger


from ouranos import db, current_app
from ouranos.core.config import get_db_dir
from ouranos.core.database.models.app import User


async def create_base_data(logger: Logger = getLogger()):
    create_db_dir = False
    if "sqlite" in current_app.config["SQLALCHEMY_DATABASE_URI"]:
        create_db_dir = True
    for uri in current_app.config["SQLALCHEMY_BINDS"].values():
        if "sqlite" in uri:
            create_db_dir = True
            break
    if create_db_dir:
        get_db_dir()
    from ouranos.core.database.models import app
    from ouranos.core.database.models import archives
    from ouranos.core.database.models import gaia
    from ouranos.core.database.models import system
    await db.create_all()
    async with db.scoped_session() as session:
        try:
            await app.CommunicationChannel.insert_channels(session)
            await app.Role.insert_roles(session)
            await app.Service.insert_services(session)
            await app.User.insert_gaia(session)
        except Exception as e:
            logger.error(e)
            raise e


async def print_registration_token(logger: Logger):
    async with db.scoped_session() as session:
        try:
            token = await User.create_invitation_token(session)
            print(f"registration token: {token}")
        except Exception as e:
            logger.error(e)
            raise e
