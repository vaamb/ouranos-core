class OuranosException(Exception):
    pass


class NoResultFound(OuranosException):
    pass


class DuplicatedEntry(OuranosException):
    pass


class NoEcosystemFound(NoResultFound):
    """No ecosystem could be found"""


class WrongDataFormat(OuranosException):
    pass



