from datetime import datetime, timedelta, timezone
from inspect import isclass
from logging import getLogger, Logger
from typing import ClassVar

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos import db, scheduler
from ouranos.core.database.models import app, archives, gaia
from ouranos.core.database.models.abc import ArchivableMixin, Base


class Archiver:
    _batch_size: ClassVar[int] = 100

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.logger: Logger = getLogger("ouranos.aggregator")
        self._mapping: dict[str, dict[str, type[ArchivableMixin]]] | None = None

    @property
    def mapping(self) -> dict[str, dict[str, type[ArchivableMixin]]]:
        if self._mapping is None:
            self._mapping = self._map_archives()
        return self._mapping

    @staticmethod
    def _get_archivable(module) -> dict[str, type[ArchivableMixin]]:
        return {
            Model.get_archive_table(): Model
            for Model in module.__dict__.values()
            if (
                    isclass(Model)
                    and issubclass(Model, ArchivableMixin)
                    and Model is not ArchivableMixin
            )
        }

    def _map_archives(self) -> dict[str, dict[str, type[ArchivableMixin | Base]]]:
        archive_models = {
            Model.__tablename__: Model
            for Model in archives.__dict__.values()
            if (
                isclass(Model)
                and issubclass(Model, Base)
                and hasattr(Model, "__table__")
            )
        }
        recent_models = {
            **self._get_archivable(app),
            **self._get_archivable(gaia),
        }
        mapping = {}
        for model_name, recent_model in recent_models.items():
            archive_model = archive_models.get(model_name)
            if not archive_model:
                self.logger.warning(
                    f"Table '{model_name}' is defined as archivable but does not "
                    f"have a linked archive table")
                continue

            mapping[model_name] = {
                "archive": archive_model,
                "recent": recent_model,
            }
        return mapping

    @classmethod
    async def _get_rows_to_archive(
            cls,
            session: AsyncSession,
            RecentModel: type[ArchivableMixin | Base],
            time_limit,
    ) -> list[dict]:
        stmt = (
            select(RecentModel)
            .where(RecentModel.get_archive_column() < time_limit)
            .order_by(RecentModel.get_archive_column().asc())
            .limit(cls._batch_size)
        )
        result = await session.execute(stmt)
        return [
            row.to_dict()
            for row in result.scalars()
        ]

    async def _archive(
            self,
            data_name: str,
            to_archive_model: type[ArchivableMixin | Base],
            archive_model: type[ArchivableMixin | Base],
    ) -> None:
        self.logger.debug(f"Archiving {data_name} data")
        limit: int | None = to_archive_model.get_time_limit()
        if limit is None:
            self.logger.debug(f"Archiving is not enabled for {data_name}")
            return

        now_utc = datetime.now(timezone.utc)
        time_limit = now_utc - timedelta(days=limit)

        async with db.scoped_session() as session:
            to_archive = await self._get_rows_to_archive(
                session, to_archive_model, time_limit)
            while to_archive:
                # Add old data in the archive table
                stmt = (
                    insert(archive_model)
                    .values(to_archive)
                )
                await session.execute(stmt)
                # Remove archived data from the current data table
                archived: list[int] = [row["id"] for row in to_archive]
                stmt = (
                    delete(to_archive_model)
                    .where(to_archive_model.id.in_(archived))
                )
                await session.execute(stmt)
                # Commit so each batch is self-contained
                await session.commit()
                # The previous rows have been deleted, get the data now at the top
                to_archive = await self._get_rows_to_archive(
                    session, to_archive_model, time_limit)

    async def archive_old_data(self) -> None:
        self.logger.info("Archiving old data")
        for data in self.mapping:
            recent = self.mapping[data]["recent"]
            archive = self.mapping[data]["archive"]
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
