from fastapi import FastAPI
from socketio import AsyncManager

from ouranos.web_server.factory import create_app, create_sio_manager


def test_create_app():
    app = create_app()
    assert isinstance(app, FastAPI)


def test_create_sio_manager():
    sio_manager = create_sio_manager()
    assert isinstance(sio_manager, AsyncManager)
