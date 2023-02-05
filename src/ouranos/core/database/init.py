from logging import Logger


from ouranos import db, current_app
from ouranos.core.config import get_db_dir


async def create_base_data(logger: Logger):
    create_db_dir = False
    if "sqlite" in current_app.config["SQLALCHEMY_DATABASE_URI"]:
        create_db_dir = True
    for uri in current_app.config["SQLALCHEMY_BINDS"].values():
        if "sqlite" in uri:
            create_db_dir = True
            break
    if create_db_dir:
        get_db_dir()
    from ouranos.core.database.models import (
        CommunicationChannel, Measure, Role, User
    )
    await db.create_all()
    async with db.scoped_session() as session:
        try:
            await CommunicationChannel.insert_channels(session)
            await Measure.insert_measures(session)
            await Role.insert_roles(session)
            await User.insert_gaia(session)
        except Exception as e:
            logger.error(e)
            raise e
