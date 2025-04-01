from datetime import datetime, timezone
from enum import Enum


START_TIME = datetime.now(timezone.utc).replace(microsecond=0)

ECOSYSTEM_TIMEOUT = 60


# File size
MAX_TEXT_FILE_SIZE = 10 * 1024 * 1024
MAX_PICTURE_FILE_SIZE = 10 * 1024 * 1024

# File extensions
SUPPORTED_TEXT_EXTENSIONS = {"md", "txt"}
SUPPORTED_IMAGE_EXTENSIONS = {"gif", "jpeg", "jpg", "png", "svg", "webp"}

# Login
SESSION_FRESHNESS = 15 * 60 * 60
SESSION_TOKEN_VALIDITY = 7 * 24 * 60 * 60

REGISTRATION_TOKEN_VALIDITY = 24 * 60 * 60


class TOKEN_SUBS(Enum):
    REGISTRATION: str = "registration"
    CONFIRMATION: str = "confirmation"
    RESET_PASSWORD: str = "reset_password"
    CAMERA_UPLOAD: str = "camera_upload"


class LOGIN_NAME(Enum):
    COOKIE: str = "session"
    HEADER: str = "Authorization"
