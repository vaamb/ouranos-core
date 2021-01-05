from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Optional, Regexp, ValidationError

from app.models import comChannel, User


class EditProfileForm(FlaskForm):
    firstname = StringField('First name', validators=[DataRequired()])
    lastname = StringField('Last name', validators=[DataRequired()])
    username = StringField('Username', validators=[
        DataRequired(), Length(1, 64),
        Regexp('^[A-Za-z][A-Za-z0-9_.]*$', 0,
               'Usernames must have only letters, numbers, dots or '
               'underscores')])
    email = StringField('Email', validators=[DataRequired(), Email()])
    daily_recap = BooleanField('Daily recap')
    channels = {"None": 0, "telegram": 1}  # comChannel.query.all().with_entities(comChannel.name),
    daily_recap_channels = SelectField("Delivery channel", choices=channels,)
    telegram = BooleanField('Telegram notifications')
    telegram_chat_id = IntegerField("Telegram chat id", validators=[Optional()])  # Length(8, 11)])  # TODO: add validators
    submit = SubmitField('Submit changes')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None and user.id != current_user.id:
            raise ValidationError('This username is already used. '
                                  'Please provide a different one.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None and user.id != current_user.id:
            raise ValidationError('This email address is already used. '
                                  'Please provide a different one.')
