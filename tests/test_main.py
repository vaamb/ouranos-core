from flask import url_for
from flask_login import login_user

from src.app import db
from src.app.models import Role, User


password = "Password1"


def create_users():
    def create_user(role):
        role_qo = db.session.query(Role).filter_by(name=role).one()
        user = User(username=f"Test{role.capitalize()}", role=role_qo)
        user.set_password(password)
        db.session.add(user)
    
    for role in ("User", "Operator", "Administrator"):
        create_user(role)

    db.session.commit()


def load_user(role="User"):
    return db.session.query(User).filter_by(
        username=f"Test{role.capitalize()}").first()


def test_unprotected_views(client):
    views = ("to_home", "home", "weather", "about", "license_", "faq")

    for view in views:
        assert client.get(url_for(f"main.{view}"),
                          follow_redirects=True).status_code == 200

    rv = client.get(url_for("main.to_home"), follow_redirects=True)
    assert rv.data == client.get(url_for("main.home")).data


def test_protected_views_anonymous(client):
    protected_views = ("care", "warnings_", "preferences")
    for view in protected_views:
        rv = client.get(url_for(f"main.{view}"), follow_redirects=True)
        assert b"Please log in to access this page" in rv.data

    rv = client.get(url_for(f"main.user_page", username="Invalid"),
                    follow_redirects=True)
    assert b"Please log in to access this page" in rv.data


def test_protected_views_user(client):
    create_users()
    user = load_user("User")
    login_user(user)

    protected_views = ("care", "warnings_", "preferences")
    for view in protected_views:
        rv = client.get(url_for(f"main.{view}"), follow_redirects=True)
        assert b"Please log in to access this page" not in rv.data

    rv = client.get(url_for(f"main.user_page", username="Invalid"),
                    follow_redirects=True)
    assert b"Please log in to access this page" not in rv.data
