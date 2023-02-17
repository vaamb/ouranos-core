import typing as t

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core import validate
from ouranos.sdk import api
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.utils import assert_single_uid


if t.TYPE_CHECKING:
    from ouranos.core.database.models.gaia import Engine


router = APIRouter(
    prefix="/engine",
    responses={404: {"description": "Not found"}},
    tags=["engine"],
)


async def engine_or_abort(session: AsyncSession, engine_id: str) -> "Engine":
    engine = await api.engine.get(
        session=session, engine_id=engine_id
    )
    if engine:
        return engine
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No ecosystem(s) found"
    )


@router.get("/", response_model=list[validate.gaia.engine])
async def get_engines(
        engines_id: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session)
):
    engines = await api.engine.get_multiple(session, engines_id)
    return engines


@router.get("/u/<uid>", response_model=validate.gaia.engine)
async def get_engine(
        uid: str,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(uid)
    engine = await engine_or_abort(session, uid)
    return engine
