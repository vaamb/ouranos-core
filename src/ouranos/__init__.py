__version__ = "0.6.0"

from ouranos.core.globals import current_app, db, scheduler
from ouranos.core.config import app_info, configure_logging, setup_config
from ouranos.core.config.base import BaseConfig as Config
from ouranos.core.utils import json, setup_loop
from ouranos.main import main, Ouranos
