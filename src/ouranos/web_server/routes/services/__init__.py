from fastapi import APIRouter

from ouranos.web_server.routes.services.calendar import router as calendar_router
from ouranos.web_server.routes.services.weather import router as weather_router
from ouranos.web_server.routes.services.wiki import router as wiki_router


router = APIRouter(
    prefix="/app/services",
    responses={404: {"description": "Not found"}},
)


router.include_router(calendar_router)
router.include_router(weather_router)
router.include_router(wiki_router)
