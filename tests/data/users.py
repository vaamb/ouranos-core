from dataclasses import dataclass
from enum import Enum


class RoleNames(Enum):
    User = "User"
    Operator = "Operator"
    Administrator = "Administrator"


@dataclass
class FakeUser:
    firstname: str
    lastname: str
    username: str
    password: str
    role: RoleNames


user = FakeUser("John", "Doe", "Who", "Password1", RoleNames.User)
operator = FakeUser("Jane", "Doe", "Her", "Password1", RoleNames.Operator)
admin = FakeUser("Nemo", "Nescio", "Me", "Password1", RoleNames.Administrator)
