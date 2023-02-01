from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column


from ouranos import db


base = db.Model


# ---------------------------------------------------------------------------
#   System-related models, located in db_system
# ---------------------------------------------------------------------------
class SystemHistory(base):
    __tablename__ = "system_history"
    __bind_key__ = "system"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(nullable=False)
    CPU_used: Mapped[float] = mapped_column(sa.Float(precision=1))
    CPU_temp: Mapped[float] = mapped_column(sa.Float(precision=1))
    RAM_total: Mapped[float] = mapped_column(sa.Float(precision=2))
    RAM_used: Mapped[float] = mapped_column(sa.Float(precision=2))
    RAM_process: Mapped[float] = mapped_column(sa.Float(precision=2))
    DISK_total: Mapped[float] = mapped_column(sa.Float(precision=2))
    DISK_used: Mapped[float] = mapped_column(sa.Float(precision=2))
