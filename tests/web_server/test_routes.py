from .routes.app import TestApp
from .routes.auth import (
    TestCurrentUser, TestLogin, TestRegister, TestRegistrationToken,
    TestUserConfirmation, TestUserResetPassword)
from .routes.calendar import TestCalendar, TestEvent
from .routes.ecosystem import (
    TestEcosystemActuators, TestEcosystemCore, TestEcosystemEnvironmentParameters,
    TestEcosystemLight, TestEcosystemManagement)
from .routes.engine import TestEngineCore
from .routes.hardware import TestHardware
from .routes.protected import (
    TestAdminProtection, TestAuthenticatedProtection, TestOperatorProtection)
from .routes.sensor import TestMeasuresAvailable, TestSensorsData, TestSensorsSkeleton
from .routes.services import TestServicesRouteProtection
from .routes.system import TestSystem
from .routes.user import TestUser
from .routes.warning import TestWarning
from .routes.weather import TestWeather
from .routes.wiki import (
    TestWikiArticles, TestWikiNotFound, TestWikiPictures, TestWikiTopics)
