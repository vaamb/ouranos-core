import datetime as dt
from enum import IntEnum
import traceback
import typing as t
from typing import Self, Sequence

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from ouranos.core.database.models.abc import Base
from ouranos.core.database.models.types import SQLIntEnum, UtcDateTime
from ouranos.core.database.models.utils import paginate, TimeWindow

if t.TYPE_CHECKING:
    import logging


class LogLevel(IntEnum):
    NOTSET = 0
    DEBUG = 10
    INFO = 20
    WARNING = 30
    WARN = WARNING
    ERROR = 40
    CRITICAL = 50
    FATAL = CRITICAL


class LogRecord(Base):
    __tablename__ = "log_records"
    __bind_key__ = "system"
    __table_args__ = (
        sa.Index("idx_log_records_timestamp_level", "timestamp", "level"),
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    timestamp: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    level: Mapped[LogLevel] = mapped_column(SQLIntEnum(LogLevel), nullable=False)
    logger_name: Mapped[str] = mapped_column(sa.String(length=128), nullable=False)
    file_name: Mapped[str] = mapped_column(sa.String(length=256), nullable=False)
    line_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    func_name: Mapped[str] = mapped_column(sa.String(length=128), nullable=False)
    message: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    traceback: Mapped[str] = mapped_column(sa.Text())

    @classmethod
    async def create(cls, session: AsyncSession, record: logging.LogRecord) -> None:
        tb = None
        if record.exc_info:
            tb = "".join(traceback.format_exception(*record.exc_info))
        insert = cls._get_insert()
        stmt = insert(cls).values(
            timestamp=dt.datetime.fromtimestamp(record.created, tz=dt.timezone.utc),
            level=LogLevel(record.levelno),
            logger_name=record.name,
            file_name=record.filename,
            line_no=record.lineno,
            func_name=record.funcName,
            message=record.getMessage(),
            traceback=tb,
        )
        await session.execute(stmt)

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            *,
            time_window: TimeWindow | None = None,
            level_min: LogLevel | None = None,
            level_max: LogLevel | None = None,
            page: int | None = None,
            per_page: int | None = 30,
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .order_by(cls.timestamp.desc())
        )
        if time_window is not None:
            stmt = time_window.modify_stmt(stmt, cls.timestamp)
        if level_min is not None:
            stmt = stmt.where(cls.level >= level_min)
        if level_max is not None:
            stmt = stmt.where(cls.level <= level_max)
        stmt = paginate(stmt, page, per_page)
        result = await session.execute(stmt)
        return result.scalars().all()
