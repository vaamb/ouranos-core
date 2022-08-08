import sqlalchemy as sa

from . import base


# ---------------------------------------------------------------------------
#   System-related models, located in db_system
# ---------------------------------------------------------------------------
class SystemHistory(base):
    __tablename__ = "system_history"
    __bind_key__ = "system"
    id = sa.Column(sa.Integer, primary_key=True)
    datetime = sa.Column(sa.DateTime, nullable=False)
    CPU_used = sa.Column(sa.Float(precision=1))
    CPU_temp = sa.Column(sa.Float(precision=1))
    RAM_total = sa.Column(sa.Float(precision=2))
    RAM_used = sa.Column(sa.Float(precision=2))
    DISK_total = sa.Column(sa.Float(precision=2))
    DISK_used = sa.Column(sa.Float(precision=2))
