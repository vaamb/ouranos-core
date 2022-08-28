import asyncio

from datetime import timedelta

from src import api


username = "TestLogin"
password = "Password1"


def test_register_new_user(event_loop, client, db):
    invitation_token = event_loop.create_task(
        api.admin.create_invitation_token(session=db.session)
    )

    rv = client.post(
        url="api/auth/register",
        params={"invitation_token": invitation_token},
        data={
            "firstname": "John",
            "lastname": "Doe",
            "email": "john.doe@test.com",
            "username": username,
            "password": password,
        },
    )

    assert b"You are now registered" in rv.data


"""
    logout(client)

    rv = client.post(url_for("auth.register"),
                     query_string={"token": f"{invitation_jwt}r"},
                     follow_redirects=True)
    assert b"token is invalid" in rv.data

    expired_invitation_token = api.admin.create_invitation_token(
        session=app.extra["db"].session,
        first_name="New_user",
        role_name="default",
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
"""
