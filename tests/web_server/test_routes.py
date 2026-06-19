from .routes.app import TestApp
from .routes.auth import (
    TestCurrentUser, TestLogin, TestRegister, TestRegistrationToken,
    TestUserConfirmation, TestUserResetPassword)
from .routes.calendar import TestCalendar, TestEvent
from .routes.ecosystem import (
    TestEcosystemActuator, TestEcosystem, TestEnvironmentParameterEcosystem,
    TestEnvironmentParameterUnique, TestEcosystemLight, TestEcosystemManagement,
    TestWeatherEventEcosystem, TestWeatherEventUnique)
from .routes.engine import (
    TestEngineCrudRequests, TestEngines, TestEngineUnique)
from .routes.hardware import (
    TestHardwareEcosystem, TestHardwareGlobal, TestHardwareUnique)
from .routes.protected import (
    TestAdminProtection, TestAuthenticatedProtection, TestOperatorProtection)
from .routes.sensor import (
    TestMeasuresAvailable, TestSensorData, TestSensorsCurrentData,
    TestSensorsSkeleton)
from .routes.services import TestServicesRouteProtection
from .routes.system import TestSystems, TestSystemUnique
from .routes.user import TestUser
from .routes.warning import TestWarning
from .routes.weather import TestWeather
from .routes.wiki import (
    TestWikiArticles, TestWikiNotFound, TestWikiPictures, TestWikiTopics)
