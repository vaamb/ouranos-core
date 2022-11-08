from fastapi import APIRouter

router = APIRouter(
    prefix="/gaia",
    responses={404: {"description": "Not found"}},
    tags=["gaia"],
)

from . import ecosystem, engine, hardware, other
