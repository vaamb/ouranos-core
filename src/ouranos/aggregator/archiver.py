import asyncio
from datetime import datetime, timedelta, timezone
from logging import getLogger, Logger
from typing import Type

from sqlalchemy import delete, insert, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.declarative import DeclarativeMeta

from ouranos import db, scheduler
from ouranos.core.database.utils import ArchiveLink
from ouranos.core.database.models import gaia, archives


# For type hint; all Tables with __archive_link__ set should have this format
class ArchivableData(DeclarativeMeta):
    __tablename__: str
    __bind_key__: str
    __archive_link__: ArchiveLink

    datetime: datetime


class Archiver:
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.logger: Logger = getLogger("ouranos.aggregator")
        self._mapping = {}

    def _map_archives(self) -> None:
        models_: list[Type[ArchivableData]] = [
            cls for name, cls in [
                *archives.__dict__.items(),
                *gaia.__dict__.items(),
            ]
            if isinstance(cls, type) and issubclass(cls, db.Model)
        ]
        for model in models_:
            link = getattr(model, '__archive_link__', None)
            if link:
                try:
                    self._mapping[link.name].update({link.status: model})
                except KeyError:
                    self._mapping[link.name] = {link.status: model}

        items = self._mapping.items()
        for name, status in items:
            if not all(s in status for s in ("recent", "archive")):
                if "recent" not in status:
                    missing = "recent"
                    cls_name = status["archive"].__class__.__name__
                else:
                    missing = "archive"
                    cls_name = status["recent"].__class__.__name__
                self.logger.warning(
                    f"Model {cls_name} has no '{missing}' ArchiveLink set"
                )
                del self._mapping[name]

    async def _archive(
            self,
            data_name: str,
            recent_model: ArchivableData,
            archive_model: ArchivableData,
    ) -> None:
        self.logger.debug(f"Archiving {data_name} data")
        limit = (
                archive_model.__archive_link__.limit or
                recent_model.__archive_link__.limit
        )
        if limit is not None:
            now_utc = datetime.now(timezone.utc)
            time_limit = now_utc - timedelta(days=limit)
            columns = inspect(recent_model).columns.keys()

            def as_list_of_dict(list_of_models: list[ArchivableData]) -> list[dict]:
                return [
                    {column: getattr(model, column) for column in columns}
                    for model in list_of_models
                ]

            async with db.scoped_session() as session:
                session: AsyncSession
                stmt = select(recent_model).where(recent_model.datetime < time_limit)
                result = await session.execute(stmt)
                old_data_obj = result.scalars().all()
                old_data = as_list_of_dict(old_data_obj)
                stmt = insert(archive_model).values(old_data)
                await session.execute(stmt)
                stmt = delete(recent_model).where(recent_model.datetime < time_limit)
                await session.execute(stmt)
                await session.commit()
        else:
            self.logger.warning(f"No limit_key set for {data_name} ArchiveLink")

    async def archive_old_data(self) -> None:
        self.logger.info("Archiving old data")
        if not self._mapping:
            self._map_archives()
        for data in self._mapping:
            recent = self._mapping[data]["recent"]
            archive = self._mapping[data]["archive"]
            await self._archive(data, recent, archive)

    async def start(self) -> None:
        self.logger.info("Scheduling the archiver")
        scheduler.add_job(
            self.archive_old_data,
            "cron", hour="1", day_of_week="0", misfire_grace_time=60 * 60,
            id="archiver"
        )

    async def stop(self) -> None:
        self.logger.info("Stopping the archiver")
        scheduler.remove_job(job_id="archiver")
