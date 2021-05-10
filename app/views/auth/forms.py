from flask_wtf import FlaskForm
import jwt
from wtforms import BooleanField, PasswordField, StringField, SubmitField, \
    IntegerField
from wtforms.validators import DataRequired, Email, EqualTo, Length, \
    Regexp, ValidationError

from app.models import User
from config import Config


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')


class InvitationForm(FlaskForm):
    token = StringField('Invitation token', validators=[DataRequired()])
    submit = SubmitField('Validate')

    def validate_token(self, token):
        try:
            decoded = jwt.decode(jwt=token.data.strip(), key=Config.JWT_SECRET_KEY,
                                 algorithms="HS256")
            user = User.query.filter(User.token == decoded["utk"]).first()
        except jwt.ExpiredSignatureError:
            raise ValidationError("This invitation token has expired")
        except jwt.InvalidSignatureError:
            raise ValidationError("This invitation token is invalid")
        except KeyError:
            raise ValidationError("This invitation token is invalid")
        if user:
            raise ValidationError("This invitation token has already been used "
                                  "for registration")


class RegistrationForm(FlaskForm):
    firstname = StringField('First name', validators=[DataRequired()])
    lastname = StringField('Last name', validators=[DataRequired()])
    username = StringField('Username', validators=[
        DataRequired(), Length(1, 64),
        Regexp('^[A-Za-z]\w*$', 0,
               'Usernames must start with a letter and be composed of letters, '
               'numbers and/or underscores')])
    telegram = IntegerField("Telegram chat id")
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[
        DataRequired(), 
        Length(min=8, message='Password must be at least 8 characters long.'),
        Regexp('.*\d.*[A-Z]|.*[A-Z].*\d', 0,
               'Password must have at least one capital letter and one '
               'number')])
    password2 = PasswordField('Confirm Password', validators=[
        DataRequired(), EqualTo('password', message='Passwords must match.')])
    submit = SubmitField('Register')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('This username is already used. '
                                  'Please provide a different one.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('This email address is already used. '
                                  'Please provide a different one.')
