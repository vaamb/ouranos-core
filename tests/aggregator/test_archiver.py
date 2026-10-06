from __future__ import annotations

from datetime import timedelta
import logging
import types

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

import gaia_validators as gv

from ouranos import current_app
from ouranos.aggregator.archiver import Archiver
from ouranos.core.database.models.abc import ArchivableMixin
from ouranos.core.database.models.archives import (
    ActuatorRecordArchive, GaiaWarningArchive, SensorDataRecordArchive)
from ouranos.core.database.models.gaia import (
    ActuatorRecord, GaiaWarning, SensorDataRecord)

import tests.data.gaia as g_data
from tests.class_fixtures import SensorsAware


class _FakeArchivable(ArchivableMixin):
    _archive_table = "fake_archive"
    _archive_column = "timestamp"

    @classmethod
    def get_time_limit(cls) -> int | None:
        return 30


def _make_module(**attrs) -> types.ModuleType:
    module = types.ModuleType("test_module")
    for name, value in attrs.items():
        setattr(module, name, value)
    return module


# ---------------------------------------------------------------------------
#   _get_archivable
# ---------------------------------------------------------------------------
def test_get_archivable_finds_subclass():
    module = _make_module(FakeModel=_FakeArchivable)
    assert Archiver._get_archivable(module) == {"fake_archive": _FakeArchivable}


def test_get_archivable_skips_non_classes():
    module = _make_module(a_string="hello", a_number=42, a_none=None, a_list=[])
    assert Archiver._get_archivable(module) == {}


def test_get_archivable_skips_mixin_itself():
    module = _make_module(ArchivableMixin=ArchivableMixin)
    assert Archiver._get_archivable(module) == {}


def test_get_archivable_skips_unrelated_classes():
    class Unrelated:
        pass

    module = _make_module(Unrelated=Unrelated)
    assert Archiver._get_archivable(module) == {}


def test_get_archivable_mixed_module():
    """Realistic case: module contains imports, constants, and models all at once."""
    class Unrelated:
        pass

    module = _make_module(
        sa="imported_module",
        a_number=42,
        Unrelated=Unrelated,
        ArchivableMixin=ArchivableMixin,
        FakeModel=_FakeArchivable,
    )
    assert Archiver._get_archivable(module) == {"fake_archive": _FakeArchivable}


# ---------------------------------------------------------------------------
#   _map_archives
# ---------------------------------------------------------------------------
def test_map_archives_warns_on_missing_archive_table(monkeypatch, caplog):
    monkeypatch.setattr("ouranos.aggregator.archiver.gaia", _make_module(FakeModel=_FakeArchivable))
    monkeypatch.setattr("ouranos.aggregator.archiver.app", _make_module())
    monkeypatch.setattr("ouranos.aggregator.archiver.archives", _make_module())

    archiver = Archiver()
    with caplog.at_level(logging.WARNING, logger="ouranos.aggregator"):
        mapping = archiver._map_archives()

    assert "fake_archive" not in mapping
    assert "fake_archive" in caplog.text


# ---------------------------------------------------------------------------
#   _archive
# ---------------------------------------------------------------------------
_ARCHIVING_PERIOD = 30  # days
_BATCH_SIZE = 3
# More old rows than `_BATCH_SIZE` so several batches are needed, and not a
#  multiple of it so the last batch is partial
_N_OLD = 2 * _BATCH_SIZE + 1
_N_RECENT = 2


def _old(i: int):
    return g_data.timestamp_now - timedelta(days=_ARCHIVING_PERIOD + 1 + i)


def _recent(i: int):
    return g_data.timestamp_now - timedelta(days=_ARCHIVING_PERIOD - 1, minutes=i)


@pytest.mark.asyncio
class TestArchive(SensorsAware):
    @pytest.fixture(autouse=True)
    def archiver_config(self, monkeypatch):
        monkeypatch.setattr(Archiver, "_batch_size", _BATCH_SIZE)
        # The config is immutable, patch the models directly
        for model in (SensorDataRecord, ActuatorRecord, GaiaWarning):
            monkeypatch.setattr(
                model, "get_time_limit", classmethod(lambda cls: _ARCHIVING_PERIOD))

    @pytest_asyncio.fixture(autouse=True)
    async def clean_tables(self, db: AsyncSQLAlchemyWrapper):
        models = (
            SensorDataRecord, SensorDataRecordArchive,
            ActuatorRecord, ActuatorRecordArchive,
            GaiaWarning, GaiaWarningArchive,
        )
        async with db.scoped_session() as session:
            for model in models:
                await session.execute(delete(model))
        yield

    @staticmethod
    async def _get_all(db: AsyncSQLAlchemyWrapper, model) -> list:
        async with db.scoped_session() as session:
            result = await session.execute(select(model).order_by(model.id))
            return [row.to_dict() for row in result.scalars()]

    async def test_archive_sensor_records(self, db: AsyncSQLAlchemyWrapper):
        def record(timestamp, value: float) -> dict:
            return {
                "ecosystem_uid": g_data.ecosystem_uid,
                "sensor_uid": g_data.sensor_record.sensor_uid,
                "measure": g_data.sensor_record.measure,
                "timestamp": timestamp,
                "value": value,
            }

        async with db.scoped_session() as session:
            await SensorDataRecord.create_multiple(session, values=[
                *[record(_old(i), i) for i in range(_N_OLD)],
                *[record(_recent(i), 100 + i) for i in range(_N_RECENT)],
            ])
        old_rows = [
            row for row in await self._get_all(db, SensorDataRecord)
            if row["value"] < 100
        ]

        await Archiver()._archive(
            "sensor_records_archive", SensorDataRecord, SensorDataRecordArchive)

        # Every old row is archived as is, not only the first batch
        assert await self._get_all(db, SensorDataRecordArchive) == old_rows
        # Only the old rows are removed from the recent table
        remaining = await self._get_all(db, SensorDataRecord)
        assert sorted(row["value"] for row in remaining) == \
            [100 + i for i in range(_N_RECENT)]

    async def test_archive_actuator_records(self, db: AsyncSQLAlchemyWrapper):
        def record(timestamp, level: float) -> dict:
            return {
                "ecosystem_uid": g_data.ecosystem_uid,
                "type": gv.HardwareType.light,
                "timestamp": timestamp,
                "active": True,
                "mode": gv.ActuatorMode.manual,
                "status": True,
                "level": level,
            }

        async with db.scoped_session() as session:
            await ActuatorRecord.create_multiple(session, values=[
                *[record(_old(i), i) for i in range(_N_OLD)],
                *[record(_recent(i), 100 + i) for i in range(_N_RECENT)],
            ])

        await Archiver()._archive(
            "actuator_records_archive", ActuatorRecord, ActuatorRecordArchive)

        archived = await self._get_all(db, ActuatorRecordArchive)
        assert sorted(row["level"] for row in archived) == list(range(_N_OLD))
        remaining = await self._get_all(db, ActuatorRecord)
        assert sorted(row["level"] for row in remaining) == \
            [100 + i for i in range(_N_RECENT)]

    async def test_archive_warnings(self, db: AsyncSQLAlchemyWrapper):
        def warning(title: str, solved_on=None) -> dict:
            return {
                **g_data.gaia_warning,
                "title": title,
                "created_on": _old(_N_OLD + 1),
                "solved_on": solved_on,
            }

        async with db.scoped_session() as session:
            await GaiaWarning.create_multiple(session, values=[
                *[warning(f"old_{i}", solved_on=_old(i)) for i in range(_N_OLD)],
                warning("recently_solved", solved_on=_recent(0)),
                # Unsolved warnings are never archived, however old they are
                warning("unsolved"),
            ])

        await Archiver()._archive("warnings_archive", GaiaWarning, GaiaWarningArchive)

        archived = await self._get_all(db, GaiaWarningArchive)
        assert sorted(row["title"] for row in archived) == \
            sorted(f"old_{i}" for i in range(_N_OLD))
        remaining = await self._get_all(db, GaiaWarning)
        assert sorted(row["title"] for row in remaining) == \
            ["recently_solved", "unsolved"]

    async def test_archive_nothing_to_archive(self, db: AsyncSQLAlchemyWrapper):
        await Archiver()._archive(
            "sensor_records_archive", SensorDataRecord, SensorDataRecordArchive)

        assert await self._get_all(db, SensorDataRecordArchive) == []

    async def test_archive_old_data_with_default_config(self, monkeypatch):
        # The weekly job must run over every mapped table with the default
        #  archiving periods, which are all `None`
        monkeypatch.undo()  # Restore the models' own `get_time_limit()`
        assert current_app.config["WARNING_ARCHIVING_PERIOD"] is None

        archiver = Archiver()
        assert set(archiver.mapping) == {
            "sensor_records_archive", "actuator_records_archive", "warnings_archive"}
        await archiver.archive_old_data()
