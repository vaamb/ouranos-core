import typing as t

from fastapi import APIRouter, Query

from ouranos.core.pydantic.models.weather import (
    PydanticCurrentWeather, PydanticHourlyWeather, PydanticDailyWeather,
    PydanticSunTimes
)
from ouranos.sdk import api
from ouranos.web_server.routes.utils import empty_result


router = APIRouter(
    prefix="/weather",
    responses={
        204: {"description": "Empty result"},
        404: {"description": "Not found"},
    },
    tags=["weather"],
)


@router.get("/sun_times", response_model=PydanticSunTimes)
async def get_sun_times() -> dict:
    response = api.sun_times.get()
    if response:
        return response
    return empty_result(response)


@router.get(path="/forecast")
async def get_forecast(exclude: t.Union[list[str], None] = Query(default=None)) -> dict:
    response = {}
    exclude = exclude or []
    if "currently" not in exclude:
        currently = api.weather.get_currently()
        if currently:
            response.update({
                "currently": currently
            })
    if "hourly" not in exclude:
        hourly = api.weather.get_hourly()
        if hourly:
            response.update({
                "hourly": hourly
            })
    if "daily" not in exclude:
        daily = api.weather.get_daily()
        if daily:
            response.update({
                "daily": daily
            })
    if response:
        return response
    return empty_result(response)


@router.get("/forecast/currently", response_model=PydanticCurrentWeather)
async def get_current_forecast() -> dict:
    response = api.weather.get_currently()
    if response:
        return response
    return empty_result(response)


@router.get("/forecast/hourly", response_model=list[PydanticHourlyWeather])
async def get_current_forecast() -> dict:
    response = api.weather.get_hourly()
    if response:
        return response
    return empty_result(response)


@router.get("/forecast/daily", response_model=list[PydanticDailyWeather])
async def get_current_forecast() -> dict:
    response = api.weather.get_daily()
    if response:
        return response
    return empty_result(response)
