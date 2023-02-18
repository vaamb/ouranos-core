import typing as t

from fastapi import APIRouter, Query

from ouranos.core import validate
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


@router.get("/sun_times", response_model=validate.weather.sun_times)
async def get_sun_times() -> dict:
    response = api.sun_times.get()
    if response:
        return response
    return empty_result(response)


@router.get(path="/forecast")
async def get_forecast(
        exclude: t.Union[list[str], None] = Query(
            default=None,
            description="Period to exclude from the forecast to choose from "
                        "'currently', 'hourly' and 'daily'"
        )
) -> dict:
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


@router.get("/forecast/currently", response_model=validate.weather.current_weather)
async def get_current_forecast() -> dict:
    response = api.weather.get_currently()
    if response:
        return response
    return empty_result(response)


@router.get("/forecast/hourly", response_model=list[validate.weather.hourly_weather])
async def get_current_forecast() -> dict:
    response = api.weather.get_hourly()
    if response:
        return response
    return empty_result(response)


@router.get("/forecast/daily", response_model=list[validate.weather.daily_weather])
async def get_current_forecast() -> dict:
    response = api.weather.get_daily()
    if response:
        return response
    return empty_result(response)
