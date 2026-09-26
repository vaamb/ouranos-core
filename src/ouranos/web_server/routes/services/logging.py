from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.app import ServiceName
from ouranos.core.database.models.logging import AccessLog, BaseLog, LogLevel
from ouranos.core.database.models.utils import TimeWindow
from ouranos.web_server.auth import is_operator
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.routes.services.utils import service_enabled
from ouranos.web_server.validate.logging import LogRecordInfo


router = APIRouter(
    prefix="/logging",
    responses={
        403: {"description": "Unauthorized"},
        404: {"description": "Not found"},
    },
    dependencies=[
        Depends(is_operator),
        Depends(service_enabled(ServiceName.logging)),
    ],
    tags=["app/services/logging"],
)


# Create a `StrEnum` to store `LogLevel` names both in lower and upper case
LogLevelName = StrEnum(
    "LogLevelName",
    [  # ty: ignore[invalid-argument-type]
        *[(i.name, i.name) for i in LogLevel],
        *[(i.name.lower(), i.name.lower()) for i in LogLevel],
    ]
)


@router.get("/base", response_model=list[LogRecordInfo])
async def get_base_logs(
        *,
        time_window: Annotated[
            TimeWindow,
            Depends(get_time_window(rounding=1, grace_time=60, max_window_length=31)),
        ],
        level_min: LogLevelName = LogLevel.INFO.name.lower(),  # ty: ignore[invalid-parameter-default]
        level_max: LogLevelName = LogLevel.CRITICAL.name.lower(),  # ty: ignore[invalid-parameter-default]
        page: Annotated[int, Query()] = 1,
        per_page: Annotated[int, Query(le=100)] = 50,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    level_min_enum = LogLevel[level_min.upper()]
    level_max_enum = LogLevel[level_max.upper()]
    return await BaseLog.get_multiple(
        session, time_window=time_window, level_min=level_min_enum,
        level_max=level_max_enum, page=page, per_page=per_page)


@router.get("/access", response_model=list[LogRecordInfo])
async def get_access_logs(
        *,
        time_window: Annotated[
            TimeWindow,
            Depends(get_time_window(rounding=1, grace_time=60, max_window_length=31)),
        ],
        level_min: LogLevelName = LogLevel.INFO.name.lower(),  # ty: ignore[invalid-parameter-default]
        level_max: LogLevelName = LogLevel.CRITICAL.name.lower(),  # ty: ignore[invalid-parameter-default]
        page: Annotated[int, Query()] = 1,
        per_page: Annotated[int, Query(le=100)] = 50,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    level_min_enum = LogLevel[level_min.upper()]
    level_max_enum = LogLevel[level_max.upper()]
    return await AccessLog.get_multiple(
        session, time_window=time_window, level_min=level_min_enum,
        level_max=level_max_enum, page=page, per_page=per_page)
