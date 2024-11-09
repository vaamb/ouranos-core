from __future__ import annotations

from fastapi import APIRouter, Response

from ouranos.core.caches import CacheFactory
from ouranos.web_server.validate.weather import (
    CurrentWeatherResponse, DailyWeatherResponse, HourlyWeatherResponse,
    SunTimesResponse)


router = APIRouter(
    prefix="/weather",
    responses={
        204: {"description": "Empty result"},
        404: {"description": "Not found"},
    },
    tags=["app/services/weather"],
)

sky_watcher_cache = CacheFactory.get("sky_watcher")


# TODO: fix this, it should not be needed
async def init_cache_if_needed():
    if not sky_watcher_cache.is_init:
        await sky_watcher_cache.init()


@router.get("/sun_times", response_model=SunTimesResponse)
async def get_sun_times():
    await init_cache_if_needed()
    response = await sky_watcher_cache.get("sun_times", None)
    if response:
        return response
    return Response(status_code=204)


@router.get("/forecast/currently", response_model=CurrentWeatherResponse)
async def get_current_forecast():
    await init_cache_if_needed()
    response = await sky_watcher_cache.get("weather_currently", None)
    if response:
        return response
    return Response(status_code=204)


@router.get("/forecast/hourly", response_model=list[HourlyWeatherResponse])
async def get_current_forecast():
    await init_cache_if_needed()
    response = await sky_watcher_cache.get("weather_hourly", None)
    if response:
        return response
    return Response(status_code=204)


@router.get("/forecast/daily", response_model=list[DailyWeatherResponse])
async def get_current_forecast():
    await init_cache_if_needed()
    response = await sky_watcher_cache.get("weather_daily", None)
    if response:
        return response
    return Response(status_code=204)
