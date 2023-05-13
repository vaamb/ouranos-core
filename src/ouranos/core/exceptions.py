class OuranosException(Exception):
    pass


class NoResultFound(OuranosException):
    pass


class DuplicatedEntry(OuranosException):
    pass


class NoEcosystemFound(NoResultFound):
    """No ecosystem could be found"""


class NotRegisteredError(OuranosException):
    pass


class WrongDataFormat(OuranosException):
    pass


class TokenError(Exception):
    pass


class ExpiredTokenError(TokenError):
    pass


class InvalidTokenError(TokenError):
    pass
