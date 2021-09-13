from datetime import timedelta

from flask import url_for

from src.app import API, db


username = "TestLogin"
password = "Password1"


def login(client, username, password):
    return client.post(
        url_for("auth.login"), data={
            "username": username,
            "password": password
        }, follow_redirects=True
    )


def logout(client):
    return client.get(url_for("auth.logout"), follow_redirects=True)


def test_register_new_user(client):
    invitation_jwt = API.admin.create_invitation_jwt(
        db_session=db.session,
        first_name="New_user",
        role="default",
    )

    rv = client.post(url_for("auth.register"),
                     query_string={"token": invitation_jwt},
                     data={
                         "firstname": "John",
                         "lastname": "Doe",
                         "email": "john.doe@test.com",
                         "username": username,
                         "password": password,
                         "password2": password,
                         },
                     follow_redirects=True)

    assert b"You are now registered" in rv.data

    logout(client)

    rv = client.post(url_for("auth.register"),
                     query_string={"token": invitation_jwt},
                     follow_redirects=True)
    assert b"already been used" in rv.data

    rv = client.post(url_for("auth.register"),
                     query_string={"token": f"{invitation_jwt}r"},
                     follow_redirects=True)
    assert b"token is invalid" in rv.data

    expired_invitation_jwt = API.admin.create_invitation_jwt(
        db_session=db.session,
        first_name="New_user",
        role="default",
        expiration_delay=timedelta(days=-7)
    )

    rv = client.get(url_for("auth.register"),
                    query_string={"token": expired_invitation_jwt},
                    follow_redirects=True)

    assert b"token has expired" in rv.data


def test_login(client):
    rv = login(client, username, password)
    assert b"You are now logged in" in rv.data

    rv = logout(client)
    assert b"You are now logged out" in rv.data

    rv = login(client, f"{username}r", password)
    assert b"Invalid username or password" in rv.data

    rv = login(client, username, f"{password}r")
    assert b"Invalid username or password" in rv.data
