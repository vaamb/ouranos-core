from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, \
    Regexp, ValidationError

from app.models import User


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')


class InvitationForm(FlaskForm):
    token = StringField('Invitation token', validators=[DataRequired()])
    submit = SubmitField('Validate')

    def validate_token(self, token):
        user = User.query.filter_by(token=token.data).first()
        if user is None:
            raise ValidationError('This invitation token is not valid. '
                                  'Please provide a different one.')


class RegistrationForm(FlaskForm):
    firstname = StringField('First name', validators=[DataRequired()])
    lastname = StringField('Last name', validators=[DataRequired()])
    username = StringField('Username', validators=[
        DataRequired(), Length(1, 64),
        Regexp('^[A-Za-z]\w*$', 0,
               'Usernames must start with a letter and be composed of letters, '
               'numbers and/or underscores')])
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
            # rem: need to push token once instantiated
            if user.token != self.token:
                raise ValidationError('This email address is already used. '
                                      'Please provide a different one.')
