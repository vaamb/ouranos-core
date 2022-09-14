import sqlalchemy as sa

from .common import (
    BaseActuatorHistory, BaseWarning, BaseHealth, BaseSensorHistory
)
from src.core.database._base import ArchiveLink


# ---------------------------------------------------------------------------
#   Models used for archiving, located in db_archive
# ---------------------------------------------------------------------------
class ArchiveActuatorHistory(BaseActuatorHistory):
    __tablename__ = "actuator_archive"
    __bind_key__ = "archive"
    __archive_link__ = ArchiveLink("actuator", "archive")

    ecosystem_uid = sa.Column(sa.String(length=8), primary_key=True)


class ArchiveSensorData(BaseSensorHistory):
    __tablename__ = "sensors_archive"
    __bind_key__ = "archive"
    __archive_link__ = ArchiveLink("sensor", "archive")

    ecosystem_uid = sa.Column(sa.String(length=8))
    sensor_uid = sa.Column(sa.String(length=16))


class ArchiveHealthData(BaseHealth):
    __tablename__ = "health_archive"
    __bind_key__ = "archive"
    __archive_link__ = ArchiveLink("health", "archive")

    ecosystem_uid = sa.Column(sa.String(length=8))


class ArchiveAppWarning(BaseWarning):
    __tablename__ = "warnings_archive"
    __bind_key__ = "archive"
    __archive_link__ = ArchiveLink("warnings", "archive")

    ecosystem_uid = sa.Column(sa.String(length=8))
