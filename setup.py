from setuptools import setup

from src.ouranos.core.config import app_info


setup(
    name=app_info["APP_NAME"].lower(),
    version=app_info["VERSION"],
)
