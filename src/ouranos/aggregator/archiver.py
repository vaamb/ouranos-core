from datetime import datetime, timedelta, timezone
from inspect import isclass
from logging import getLogger, Logger

from sqlalchemy import delete

from ouranos import db, scheduler
from ouranos.core.database.models import app, archives, gaia
from ouranos.core.database.models.abc import ArchivableMixin, Base


class Archiver:
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

    def _map_archives(self) -> dict[str, dict[str, type[ArchivableMixin]]]:
        archive_models = {
            Model.__tablename__: Model
            for Model in archives.__dict__.values()
            if issubclass(Model, Base)
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

    @staticmethod
    async def _get_archives(
            session,
            Model: type[ArchivableMixin],
            time_limit,
            offset: int,
            per_page: int = 250,
    ) ->list[dict]:
        stmt = Model._generate_get_query(
            offset=offset, limit=per_page,
            order_by=Model.get_archive_column().asc())
        stmt = stmt.where(Model.get_archive_column() < time_limit)
        result = await session.execute(stmt)
        return [
            row.to_dict()
            for row in result.scalars()
        ]

    async def _archive(
            self,
            data_name: str,
            RecentModel: type[ArchivableMixin | Base],
            ArchiveModel: type[Base],
    ) -> None:
        self.logger.debug(f"Archiving {data_name} data")
        limit = RecentModel.get_time_limit()
        if limit is None:
            self.logger.warning(f"No limit_key set for {data_name} ArchiveLink")
            return

        now_utc = datetime.now(timezone.utc)
        time_limit = now_utc - timedelta(days=limit)

        async with (db.scoped_session() as session):
            async with session.begin():
                per_page = 250
                offset = 0
                to_archive = await self._get_archives(
                    session, RecentModel, time_limit, offset, per_page)
                while to_archive:
                    await ArchiveModel.create_multiple(
                        session, values=to_archive, _on_conflict_do="update")
                    offset += per_page
                    to_archive = await self._get_archives(
                        session, RecentModel, time_limit, offset, per_page)
                stmt = (
                    delete(RecentModel)
                    .where(RecentModel.get_archive_column() < time_limit)
                )
                await session.execute(stmt)

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
