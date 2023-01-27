from logging import Logger


from ouranos import db


async def create_base_data(logger: Logger):
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
