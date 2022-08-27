from collections import namedtuple


FakeUser = namedtuple(
    "FakeUser",
    ("firstname", "lastname", "username", "password", "role")
)

auth_user = FakeUser("Foo", "Bar", "FooBar", "Password1", "User")
user = FakeUser("John", "Doe", "Him", "Password1", "User")
operator = FakeUser("Jane", "Doe", "Her", "Password1", "Operator")
admin = FakeUser("Nemo", "Nescio", "Moi", "Password1", "Administrator")
