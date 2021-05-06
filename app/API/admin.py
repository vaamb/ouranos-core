from datetime import datetime, timedelta, timezone
import secrets

from email_validator import validate_email, EmailNotValidError
from flask import render_template
from sqlalchemy.orm.exc import NoResultFound
import jwt

from app.email import send_email
from app.models import User, Role, System
from config import Config


"""
Users-related API
"""


def get_user_query_obj(user: str, session):
    return (session.query(User)
            .filter((User.id == user) |
                    (User.username == user))
            .first()
            )


def user_roles_available() -> list:
    """
    Get the name of the roles available

    :return: list, a list with the name of the roles available
    """

    roles = Role.query.all()
    return [role.name for role in roles]


def create_user_token(db_session):
    """
    Create a user token which the user can use to access API services

    :param db_session: a sqlalchemy session object
    :return: a 16 number-long hex
    """
    while True:
        user_token = secrets.token_hex(16)
        user = db_session.query(Role).filter(User.token == user_token).first()
        if not user:
            break
    return user_token


def create_invitation_jwt(db_session,
                          first_name: str = None,
                          last_name: str = None,
                          email_address: str = None,
                          telegram_chat_id: int = None,
                          role: str = "default",
                          expiration_delay: timedelta = timedelta(days=7),
                          ) -> str:
    """
    Create an invitation JSON web token

    :param db_session: a sqlalchemy session object
    :param first_name: str, the invited user first name.
    :param last_name: str, the invited user last name.
    :param email_address:  str, the invited user email address.
    :param telegram_chat_id: int, the invited user telegram chat id.
    :param role: str, the name of the invited user role. These names are
                 defined in models but can be accessed with the function
                 ``API.admin.user_roles_available()``
    :param expiration_delay: timedelta, the delay after which the invitation
                             token will be considered expired.
    :return: str, an JSON web token which can be used to register the user
    """

    email = None
    if email_address:
        try:
            email = validate_email(email_address.strip()).email
        except EmailNotValidError as e:
            # TODO: deal with this error which should technically not occur
            print(e)

    default_role = db_session.query(Role).filter_by(default=True).one().name
    if role == default_role:
        role_name = None
    else:
        try:
            role_name = db_session.query(Role).filter_by(name=role).one().name
            if role_name == default_role:
                role_name = None
        except NoResultFound:
            role_name = None

    tkn_claims = {
        "fnm": first_name,
        "lnm": last_name,
        "eml": email,
        "tgm": telegram_chat_id,
        "rle": role_name,
        "exp": datetime.now(timezone.utc) + expiration_delay,
    }

    jwt_tkn = {"utk": create_user_token(db_session=db_session)}
    for claim in tkn_claims:
        if tkn_claims[claim]:
            jwt_tkn.update({claim: tkn_claims[claim]})

    return jwt.encode(jwt_tkn, key=Config.JWT_SECRET_KEY, algorithm="HS256").decode("utf-8")


def send_invitation(invitation_jwt, mode="email"):
    decoded = jwt.decode(invitation_jwt, options={"verify_signature": False})
    firstname = decoded.get("fnm")
    text = render_template("messages/invitation.txt",
                           firstname=firstname, invitation_jwt=invitation_jwt)
    html = render_template("messages/invitation.html",
                           firstname=firstname, invitation_jwt=invitation_jwt)
    if mode == "email":
        try:
            recipient = decoded["eml"]
        except KeyError:
            raise Exception("No email address present in the JSON Web Token")
        send_email(subject="Welcome to GAIA",
                   sender="GAIA team",
                   recipients=[recipient],
                   text_body=text,
                   html_body=html,
                   sync=True)
    elif mode == "telegram":
        try:
            recipient = decoded["tgm"]
        except KeyError:
            raise Exception("No email address present in the JSON Web Token")


def get_system_data(db_session, days=7):
    time_limit = datetime.now(tz=timezone.utc) - timedelta(days=days)
    data = (db_session.query(System).filter(System.datetime >= time_limit)
                      .with_entities(System.datetime,
                                     System.CPU_used, System.CPU_temp,
                                     System.RAM_used, System.RAM_total,
                                     System.DISK_used, System.DISK_total)
                      .all()
            )
    return data
