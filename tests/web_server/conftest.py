from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from ouranos.core.config import ConfigDict
from ouranos.core.config.consts import LOGIN_NAME
from ouranos.core.dispatchers import DispatcherFactory
from ouranos.web_server.auth import SessionInfo
from ouranos.web_server.factory import create_app

from tests.utils import MockAsyncDispatcher
from tests.data.auth import user, operator, admin


@pytest.fixture(scope="module")
def app(config: ConfigDict):
    return create_app(config)


@pytest.fixture(scope="module")
def base_client(app: FastAPI):
    return TestClient(app)


@pytest.fixture(scope="function")
def client(base_client: TestClient):
    base_client.cookies = None
    return base_client


def get_user_cookie(user_id) -> dict:
    payload = SessionInfo(id="session_id", user_id=user_id, remember=True)
    token = payload.to_token()
    return {LOGIN_NAME.COOKIE.value: token}


@pytest.fixture(scope="function")
def client_user(client: TestClient):
    client.cookies = get_user_cookie(user.id)
    return client


@pytest.fixture(scope="function")
def client_operator(client: TestClient):
    client.cookies = get_user_cookie(operator.id)
    return client


@pytest.fixture(scope="function")
def client_admin(client: TestClient):
    client.cookies = get_user_cookie(admin.id)
    return client


@pytest.fixture(scope="module")
def mock_dispatcher_module():
    mock_dispatcher = MockAsyncDispatcher("application-internal")
    DispatcherFactory._DispatcherFactory__dispatchers["application-internal"] = mock_dispatcher
    return mock_dispatcher


@pytest.fixture(scope="function")
def mock_dispatcher(mock_dispatcher_module):
    mock_dispatcher_module.clear_store()
    return mock_dispatcher_module
