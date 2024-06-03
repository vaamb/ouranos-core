import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from ouranos.core.database import ArchiveLink
from ouranos.core.database.models.gaia import (
    BaseActuatorRecord, BaseHealthRecord, BaseSensorDataRecord)


# ---------------------------------------------------------------------------
#   Models used for archiving, located in db_archive
# ---------------------------------------------------------------------------
class ActuatorRecordArchive(BaseActuatorRecord):
    __tablename__ = "actuator_records_archive"
    __bind_key__ = "archive"
    __archive_link__ = ArchiveLink(
        "actuator_records", "archive", "ACTUATOR_ARCHIVING_PERIOD"
    )

    ecosystem_uid: Mapped[str] = mapped_column(sa.String(length=8), index=True)
    actuator_uid: Mapped[str] = mapped_column(sa.String(length=16), index=True)


class SensorDataRecordArchive(BaseSensorDataRecord):
    __tablename__ = "sensor_records_archive"
    __bind_key__ = "archive"
    __archive_link__ = ArchiveLink(
        "sensor_records", "archive", "SENSOR_ARCHIVING_PERIOD"
    )

    measure: Mapped[str] = mapped_column(sa.String(length=32), index=True)
    ecosystem_uid: Mapped[str] = mapped_column(sa.String(length=8), index=True)
    sensor_uid: Mapped[str] = mapped_column(sa.String(length=16), index=True)


class HealthRecordArchive(BaseHealthRecord):
    __tablename__ = "health_records_archive"
    __bind_key__ = "archive"
    __archive_link__ = ArchiveLink(
        "health_records", "archive", "HEALTH_ARCHIVING_PERIOD"
    )

    ecosystem_uid: Mapped[str] = mapped_column(sa.String(length=8), index=True)
