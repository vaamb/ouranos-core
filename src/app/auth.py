from flask_login import AnonymousUserMixin

from . import db, jwtManager, login_manager
from src.database.models.app import User


class AnonymousUser(AnonymousUserMixin):
    def can(self, perm):
        return False


login_manager.anonymous_user = AnonymousUser


@jwtManager.user_identity_loader
def user_identity_lookup(user):
    return user.id


@jwtManager.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    user_id = jwt_data["sub"]
    return get_user(user_id)


@login_manager.user_loader
def load_user(user_id):
    return get_user(user_id)


def get_user(user_id: int) -> User:
    return db.session.query(User).filter_by(id=user_id).one_or_none()
