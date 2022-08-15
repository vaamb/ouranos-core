from fastapi import FastAPI, APIRouter

from .docs import tags_metadata
from .routes import weather
from config import Config


app = FastAPI(
    title=Config.APP_NAME,
    version=Config.VERSION,
    openapi_tags=tags_metadata,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

prefix = APIRouter(prefix="/api")

prefix.include_router(weather.router)

app.include_router(prefix)
