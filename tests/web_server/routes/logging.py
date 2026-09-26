import logging

from fastapi.testclient import TestClient
import pytest
import pytest_asyncio

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.app import Service, ServiceName
from ouranos.core.database.models.logging import AccessLog, BaseLog, LogLevel

from tests.class_fixtures import UsersAware


class LogsAware:
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def add_logs(self, db: AsyncSQLAlchemyWrapper):
        def _make_record(level: int, msg: str) -> logging.LogRecord:
            return logging.LogRecord(
                name="ouranos.test", level=level, pathname=__file__, lineno=1, msg=msg,
                args=(), exc_info=None, func="test_func")

        async with db.scoped_session() as session:
            for level, msg in (
                    (logging.DEBUG, "base debug"),
                    (logging.INFO, "base info"),
                    (logging.WARNING, "base warning"),
                    (logging.ERROR, "base error"),
            ):
                await BaseLog.create(session, _make_record(level, msg))
            await AccessLog.create(session, _make_record(logging.INFO, "access info"))


class LoggingEnabled:
    # Cannot be a simple `ServicesEnabled` as logging service requires `LOG_TO_DB`
    # to be set to True in order to be enabled.
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def enable_logging(self, db: AsyncSQLAlchemyWrapper):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(Service, "_check_logging_config_requirements", lambda: True)
            async with db.scoped_session() as session:
                await Service.update(
                    session, name=ServiceName.logging, values={"status": True})


class TestLoggingDisabled(UsersAware, LogsAware):
    def test_base_logs_locked(self, client_operator: TestClient):
        response = client_operator.get("/api/app/services/logging/base")
        assert response.status_code == 423

    def test_access_logs_locked(self, client_operator: TestClient):
        response = client_operator.get("/api/app/services/logging/access")
        assert response.status_code == 423


class TestLogging(LoggingEnabled, UsersAware, LogsAware):
    def test_failure_anon(self, client: TestClient):
        response = client.get("/api/app/services/logging/base")
        assert response.status_code == 403

    def test_failure_user(self, client_user: TestClient):
        response = client_user.get("/api/app/services/logging/base")
        assert response.status_code == 403

    def test_base_logs(self, client_operator: TestClient):
        response = client_operator.get("/api/app/services/logging/base")
        assert response.status_code == 200

        data = json.loads(response.text)
        # DEBUG is filtered out by the default `level_min` (INFO), and the
        # access log lives in another table
        assert {log["message"] for log in data} == \
               {"base info", "base warning", "base error"}
        log = next(log for log in data if log["message"] == "base warning")
        assert log["level"] == LogLevel.WARNING.value
        assert log["logger_name"] == "ouranos.test"
        assert log["func_name"] == "test_func"
        assert log["traceback"] is None
        assert "id" not in log

    def test_base_logs_level_range(
            self,
            client_operator: TestClient,
    ):
        # Debug level can be provided both in lower and upper case
        level_min = "debug"
        level_max = "INFO"
        response = client_operator.get(
            "/api/app/services/logging/base",
            params={"level_min": level_min, "level_max": level_max},
        )
        assert response.status_code == 200

        data = json.loads(response.text)
        assert {log["message"] for log in data} == {"base debug", "base info"}

    @pytest.mark.parametrize("level", ["wrong", 25])
    def test_base_logs_failure_wrong_level(
            self,
            client_operator: TestClient,
            level: str | int,
    ):
        response = client_operator.get(
            "/api/app/services/logging/base", params={"level_min": level})
        assert response.status_code == 422

    def test_base_logs_pagination(self, client_operator: TestClient):
        params = {"level_min": "DEBUG", "per_page": 3}
        first_page = json.loads(client_operator.get(
            "/api/app/services/logging/base", params={**params, "page": 1}).text)
        second_page = json.loads(client_operator.get(
            "/api/app/services/logging/base", params={**params, "page": 2}).text)

        assert len(first_page) == 3
        assert len(second_page) == 1
        messages = {log["message"] for log in first_page + second_page}
        assert len(messages) == 4

    def test_base_logs_failure_per_page_too_high(self, client_operator: TestClient):
        response = client_operator.get(
            "/api/app/services/logging/base", params={"per_page": 101})
        assert response.status_code == 422

    def test_access_logs(self, client_operator: TestClient):
        response = client_operator.get("/api/app/services/logging/access")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert [log["message"] for log in data] == ["access info"]

    def test_access_logs_level_min(self, client_operator: TestClient):
        response = client_operator.get(
            "/api/app/services/logging/access", params={"level_min": "warning"})
        assert response.status_code == 200
        assert json.loads(response.text) == []
