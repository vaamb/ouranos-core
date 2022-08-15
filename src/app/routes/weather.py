import typing as t

from fastapi import APIRouter, Query

from src import api

router = APIRouter(
    prefix="/weather",
    responses={404: {"description": "Not found"}},
    tags=["weather"],
)


@router.get("/sun_times")
async def get_sun_times() -> dict:
    response = api.weather.get_suntimes_data()
    return response


@router.get("/forecast")
async def get_forecast(exclude: t.Union[list[str], None] = Query(default=None)) -> dict:
    response = {}
    if "currently" not in exclude:
        response.update({
            "currently": api.weather.get_current_weather()
        })
    if "hourly" not in exclude:
        response.update({
            "hourly": api.weather.get_hourly_weather_forecast()
        })
    if "daily" not in exclude:
        response.update({
            "daily": api.weather.get_daily_weather_forecast()
        })
    return response


@router.get("/forecast/currently")
async def get_current_forecast() -> dict:
    response = api.weather.get_current_weather()
    return response


@router.get("/forecast/hourly")
async def get_current_forecast() -> dict:
    response = api.weather.get_hourly_weather_forecast()
    return response


@router.get("/forecast/daily")
async def get_current_forecast() -> dict:
    response = api.weather.get_daily_weather_forecast()
    return response
