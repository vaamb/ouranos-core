from __future__ import annotations

from fastapi import APIRouter, Query, Response

from ouranos.core.cache import SunTimesCache, WeatherCache
from ouranos.web_server.validate.response.weather import (
    CurrentWeatherResponse, DailyWeatherResponse, HourlyWeatherResponse, SunTimesResponse)


router = APIRouter(
    prefix="/weather",
    responses={
        204: {"description": "Empty result"},
        404: {"description": "Not found"},
    },
    tags=["weather"],
)


@router.get("/sun_times", response_model=SunTimesResponse)
async def get_sun_times():
    response = SunTimesCache.get()
    if response:
        return response
    return Response(status_code=204)


@router.get(path="/forecast")
async def get_forecast(
        exclude: list[str] | None = Query(
            default=None,
            description="Period to exclude from the forecast to choose from "
                        "'currently', 'hourly' and 'daily'"
        )
):
    response = {}
    exclude = exclude or []
    if "currently" not in exclude:
        currently = WeatherCache.get_currently()
        if currently:
            response.update({
                "currently": currently
            })
    if "hourly" not in exclude:
        hourly = WeatherCache.get_hourly()
        if hourly:
            response.update({
                "hourly": hourly
            })
    if "daily" not in exclude:
        daily = WeatherCache.get_daily()
        if daily:
            response.update({
                "daily": daily
            })
    if response:
        return response
    return Response(status_code=204)


@router.get("/forecast/currently", response_model=CurrentWeatherResponse)
async def get_current_forecast():
    response = WeatherCache.get_currently()
    if response:
        return response
    return Response(status_code=204)


@router.get("/forecast/hourly", response_model=list[HourlyWeatherResponse])
async def get_current_forecast():
    response = WeatherCache.get_hourly()
    if response:
        return response
    return Response(status_code=204)


@router.get("/forecast/daily", response_model=list[DailyWeatherResponse])
async def get_current_forecast():
    response = WeatherCache.get_daily()
    if response:
        return response
    return Response(status_code=204)
