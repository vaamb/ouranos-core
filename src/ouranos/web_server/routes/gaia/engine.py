import typing as t

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core import validate
from ouranos.core.database.models.gaia import Engine
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.utils import assert_single_uid


router = APIRouter(
    prefix="/engine",
    responses={404: {"description": "Not found"}},
    tags=["gaia/engine"],
)


async def engine_or_abort(session: AsyncSession, engine_id: str) -> "Engine":
    engine = await Engine.get(
        session=session, engine_id=engine_id)
    if engine:
        return engine
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No ecosystem(s) found"
    )


@router.get("", response_model=list[validate.gaia.engine])
async def get_engines(
        engines_id: t.Optional[list[str]] = Query(
            default=None, description="A list of engine ids (either uids or sids) or "
                                      "'recent' or 'connected'"),
        session: AsyncSession = Depends(get_session)
):
    engines = await Engine.get_multiple(session, engines_id)
    return engines


@router.get("/u/{id}", response_model=validate.gaia.engine)
async def get_engine(
        id: str = Query(description="An engine id, either its uid or its sid"),
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    engine = await engine_or_abort(session, id)
    return engine
