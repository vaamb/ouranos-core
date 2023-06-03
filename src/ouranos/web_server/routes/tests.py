from fastapi import APIRouter, Depends

from ouranos.web_server.auth import is_admin, is_authenticated, is_operator


router = APIRouter(
    prefix="/tests",
    responses={404: {"description": "Not found"}},
    tags=["tests"],
)


@router.get("/is_authenticated", dependencies=[Depends(is_authenticated)])
async def get_is_authenticated():
    return "Success"


@router.get("/is_operator", dependencies=[Depends(is_operator)])
async def get_is_operator():
    return "Success"


@router.get("/is_admin", dependencies=[Depends(is_admin)])
async def get_is_admin():
    return "Success"
