import typing as t

from fastapi import APIRouter, HTTPException, Query, status

from src import api
from src.app.pydantic.models.weather import (
    PydanticCurrentWeather, PydanticHourlyWeather, PydanticDailyWeather,
    PydanticSunTimes
)


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
    response = api.weather.get_suntimes_data()
    if response:
        return response
    raise HTTPException(
        status_code=status.HTTP_204_NO_CONTENT,
        detail="Empty result",
    )


@router.get(
    path="/forecast",
    response_model=dict[
        str, t.Union[
            PydanticCurrentWeather,
            list[PydanticHourlyWeather],
            list[PydanticDailyWeather]
        ]
    ]
)
async def get_forecast(exclude: t.Union[list[str], None] = Query(default=None)) -> dict:
    response = {}
    if "currently" not in exclude:
        currently = api.weather.get_current_weather()
        if currently:
            response.update({
                "currently": currently
            })
    if "hourly" not in exclude:
        hourly = api.weather.get_hourly_weather_forecast()
        if hourly:
            response.update({
                "hourly": hourly
            })
    if "daily" not in exclude:
        daily = api.weather.get_daily_weather_forecast()
        if daily:
            response.update({
                "daily": daily
            })
    if response:
        return response
    raise HTTPException(
        status_code=status.HTTP_204_NO_CONTENT,
        detail="Empty result",
    )


@router.get("/forecast/currently", response_model=PydanticCurrentWeather)
async def get_current_forecast() -> dict:
    response = api.weather.get_current_weather()
    if response:
        return response
    raise HTTPException(
        status_code=status.HTTP_204_NO_CONTENT,
        detail="Empty result",
    )


@router.get("/forecast/hourly", response_model=list[PydanticHourlyWeather])
async def get_current_forecast() -> dict:
    response = api.weather.get_hourly_weather_forecast()
    if response:
        return response
    raise HTTPException(
        status_code=status.HTTP_204_NO_CONTENT,
        detail="Empty result",
    )


@router.get("/forecast/daily", response_model=list[PydanticDailyWeather])
async def get_current_forecast() -> dict:
    response = api.weather.get_daily_weather_forecast()
    if response:
        return response
    raise HTTPException(
        status_code=status.HTTP_204_NO_CONTENT,
        detail="Empty result",
    )
