from fastapi import APIRouter

from ouranos.web_server.routes.gaia.ecosystem import router as ecosystem_router
from ouranos.web_server.routes.gaia.engine import router as engine_router
from ouranos.web_server.routes.gaia.hardware import router as hardware_router
from ouranos.web_server.routes.gaia.sensor import router as sensor_router
from ouranos.web_server.routes.gaia.warning import router as warning_router

router = APIRouter(
    prefix="/gaia",
    responses={404: {"description": "Not found"}},
)

router.include_router(engine_router)
router.include_router(ecosystem_router)
router.include_router(hardware_router)
router.include_router(sensor_router)
router.include_router(warning_router)
