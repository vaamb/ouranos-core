from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.app import Service, ServiceName
from ouranos.web_server.dependencies import get_session


class service_enabled:
    def __init__(self, service_name: ServiceName | str):
        self.service_name = ServiceName(service_name)

    async def __call__(self, session: AsyncSession = Depends(get_session)):
        service = await Service.get(session, name=self.service_name)
        if service is None or not service.status:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Service '{self.service_name}' is not currently enabled",
            )
