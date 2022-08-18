from fastapi import FastAPI, APIRouter

from .docs import tags_metadata

from config import Config


app = FastAPI(
    title=Config.APP_NAME,
    version=Config.VERSION,
    openapi_tags=tags_metadata,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

prefix = APIRouter(prefix="/api")

from .routes.app import router as app_router
prefix.include_router(app_router)

from .routes.auth import router as auth_router
prefix.include_router(auth_router)

from .routes.weather import router as weather_router
prefix.include_router(weather_router)

app.include_router(prefix)
