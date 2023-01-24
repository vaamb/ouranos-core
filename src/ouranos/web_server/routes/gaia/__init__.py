from fastapi import APIRouter

router = APIRouter(
    prefix="/gaia",
    responses={404: {"description": "Not found"}},
    tags=["gaia"],
)

from ouranos.web_server.routes.gaia import ecosystem, engine, hardware, other
