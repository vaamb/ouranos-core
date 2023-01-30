__version__ = "0.5.3"

from ouranos.core.globals import current_app, db, scheduler
from ouranos.core.config import app_info, configure_logging, setup as setup_config
from ouranos.core.config.base import BaseConfig as Config
from ouranos.main import main, Ouranos
