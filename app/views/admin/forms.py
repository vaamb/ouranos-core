from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, IntegerField, SelectField
from wtforms.validators import DataRequired, Email, ValidationError, Optional

from app.models import User


class InvitationForm(FlaskForm):
    firstname = StringField('First name', validators=[Optional()])
    lastname = StringField('Last name', validators=[Optional()])
    email = StringField('Email', validators=[Optional(), Email()])
    role = SelectField(
        "User role",
        choices=[('User', 'User'), ('Operator', 'Operator'),
                 ('Administrator', 'Administrator')],
        validators=[DataRequired()]
    )
    telegram_chat_id = IntegerField("Telegram chat id", validators=[Optional()])
    expiration = IntegerField(
        "Days before expiration", validators=[DataRequired()]
    )
    invitation_channel = SelectField(
        "Invitation channel",
        choices=[('link', 'Link to send'), ('email', 'Email'),
                 ('telegram', 'Telegram')],
        validators=[DataRequired()]
    )
    submit = SubmitField('Send invitation')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('This email address is already used. '
                                  'Please provide a different one.')

    def validate_invitation_channel(self, invitation_channel):
        if invitation_channel.data == "email":
            if not self.email.data:
                self.email.errors.append(
                    "'Email' is required when the invitation channel is set "
                    "to 'Email'")
                raise ValidationError
        if invitation_channel.data == "telegram":
            if not self.telegram_chat_id.data:
                self.telegram_chat_id.errors.append(
                    "'Telegram chat id' is required when the invitation "
                    "channel is set to 'Telegram'")
                raise ValidationError
