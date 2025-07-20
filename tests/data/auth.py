from dataclasses import dataclass
from enum import Enum


class RoleNames(Enum):
    User = "User"
    Operator = "Operator"
    Administrator = "Administrator"


@dataclass
class FakeUser:
    id: int
    firstname: str
    lastname: str
    username: str
    password: str
    role: RoleNames

    @property
    def email(self) -> str:
        return f"{self.username}@fakemail.com"


user = FakeUser(5, "John", "Doe", "Who", "Password1!", RoleNames.User)
operator = FakeUser(6, "Jane", "Doe", "Her", "Password1!", RoleNames.Operator)
admin = FakeUser(7, "Nemo", "Nescio", "Me", "Password1!", RoleNames.Administrator)
