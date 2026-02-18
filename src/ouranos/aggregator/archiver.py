from datetime import datetime, timedelta, timezone
from inspect import isclass
from logging import getLogger, Logger

from sqlalchemy import delete

from ouranos import db, scheduler
from ouranos.core.database.models import app, archives, gaia
from ouranos.core.database.models.abc import ArchivableMixin


def _get_archivable(module) -> dict[str, type[ArchivableMixin]]:
    return {
        Model.get_archive_link().name: Model
        for Model in module.__dict__.values()
        if (
                isclass(Model)
                and issubclass(Model, ArchivableMixin)
                and not Model is ArchivableMixin
        )
    }


class Archiver:
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.logger: Logger = getLogger("ouranos.aggregator")
        self._mapping: dict[str, dict[str, type[ArchivableMixin]]] = {}

    @property
    def mapping(self) -> dict[str, dict[str, type[ArchivableMixin]]]:
        if self._mapping is None:
            self._mapping = self._map_archives()
        return self._mapping

    @staticmethod
    def _map_archives() -> dict[str, dict[str, type[ArchivableMixin]]]:
        archive_models = _get_archivable(archives)
        recent_models = {
            **_get_archivable(app),
            **_get_archivable(gaia),
        }
        mapping = {}
        for model_name, archive_model in archive_models.items():
            recent_model = recent_models.get(model_name)
            if not recent_model:
                continue

            mapping[model_name] = {
                "archive": archive_model,
                "recent": recent_model,
            }
        return mapping

    async def _archive(
            self,
            data_name: str,
            RecentModel: type[ArchivableMixin],
            ArchiveModel: type[ArchivableMixin],
    ) -> None:
        self.logger.debug(f"Archiving {data_name} data")
        limit = (
                ArchiveModel.get_archive_link().limit or
                RecentModel.get_archive_link().limit
        )
        if limit is None:
            self.logger.warning(f"No limit_key set for {data_name} ArchiveLink")
            return

        now_utc = datetime.now(timezone.utc)
        time_limit = now_utc - timedelta(days=limit)

        async with db.scoped_session() as session:
            async with session.begin():
                per_page = 250
                offset = 0
                stmt = RecentModel._generate_get_query(offset=offset, limit=per_page)
                stmt = stmt.where(RecentModel.timestamp < time_limit)
                to_archive: list[dict] = [
                    row.to_dict()
                    for row in await session.execute(stmt)
                ]
                while to_archive:
                    await ArchiveModel.create_multiple(
                        session, values=to_archive, _on_conflict_do="update")

                    offset += per_page
                    stmt = RecentModel._generate_get_query(offset=offset, limit=per_page)
                    stmt = stmt.where(RecentModel.timestamp < time_limit)
                    to_archive: list[dict] = [
                        row.to_dict()
                        for row in await session.execute(stmt)
                    ]
                stmt = delete(RecentModel).where(RecentModel.timestamp < time_limit)
                await session.execute(stmt)
                await session.commit()

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
