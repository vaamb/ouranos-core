import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from ouranos.core.database.models.gaia import (
    BaseActuatorRecord, BaseGaiaWarning, BaseSensorDataRecord)


# ---------------------------------------------------------------------------
#   Models used for archiving, located in db_archive
# ---------------------------------------------------------------------------
class ActuatorRecordArchive(BaseActuatorRecord):
    __tablename__ = "actuator_records_archive"
    __bind_key__ = "archive"

    ecosystem_uid: Mapped[str] = mapped_column(sa.String(length=8), index=True)


class SensorDataRecordArchive(BaseSensorDataRecord):
    __tablename__ = "sensor_records_archive"
    __bind_key__ = "archive"

    measure: Mapped[str] = mapped_column(sa.String(length=32), index=True)
    ecosystem_uid: Mapped[str] = mapped_column(sa.String(length=8), index=True)
    sensor_uid: Mapped[str] = mapped_column(sa.String(length=16), index=True)


class GaiaWarningArchive(BaseGaiaWarning):
    __tablename__ = "warnings_archive"
    __bind_key__ = "archive"

    created_by: Mapped[str] = mapped_column(sa.String(length=8), index=True)
