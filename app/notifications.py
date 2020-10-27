from datetime import datetime, timezone, timedelta
import logging
from time import sleep

import requests
from sqlalchemy.orm.exc import NoResultFound

from app import app_name, scheduler
from app.database import out_of_Flask_db as db
from app.models import Data, Ecosystem, Hardware, User
from config import Config

base_logger = logging.getLogger(f"{app_name}.notification")


class baseNotification:
    summary_sep = "=================================&n".lstrip()
    ecosystem_summary_sep = "---------------------------------&n&n".rstrip()

    @staticmethod
    def get_notification_recipients_id():
        recipients_id = []
        recipients = db.session.query(User).filter(
            User.notifications == True).all()
        for recipient in recipients:
            recipients_id.append(recipient.id)
        db.close_scope()
        return recipients_id

    @staticmethod
    def summarize_data():
        last_24h = datetime.now(timezone.utc) - timedelta(days=1)
        for ecosystem in db.session.query(Ecosystem).filter(
                Ecosystem.status == True):
            # TODO: average the sensors data for last 24h
            # TODO: average weather data
            pass
        db.close_scope()

    @staticmethod
    def create_recap_message(summarized_data, digested_weather,
                             digested_warnings):
        measure_unit = {"temperature": "°C", "humidity": "% hum",
                        "light": "lux"}

        today = datetime.now().strftime("%A %d %B")

        ecosystems_summary = "Yesterday sensors average:&n&n"
        for i, ecosystem in enumerate(summarized_data):
            indent = (len(ecosystem)) * " "
            for j, measure in enumerate(summarized_data[ecosystem]):
                unit = measure_unit.get(measure, "")
                if j == 0:
                    left = ecosystem
                else:
                    left = indent
                ecosystems_summary += \
                    (f"{left} - {measure}: " +
                     f"{summarized_data[ecosystem][measure]}{unit}&n")
            if i < len(summarized_data) - 1:
                ecosystems_summary += baseNotification.ecosystem_summary_sep

        template = f"""
GAIA daily recap for {today}'&n
{baseNotification.summary_sep}
{ecosystems_summary}
{baseNotification.summary_sep}
Today's weather will be
{digested_weather['morning']}°C in the
morning, {digested_weather['afternoon']}°C
in the afternoon and
{digested_weather['night']}°C during the night.&n
It will be {digested_weather['summary']}.&n
{baseNotification.summary_sep}
Don't forget to water and feed
your plants&n
{baseNotification.summary_sep}
{digested_warnings}&n
{baseNotification.summary_sep}
Have a nice day!&n
""".strip("\n")

        return template.replace('\n', ' ').replace('&n', '\n')


class telegramBot(baseNotification):
    METHOD = "Telegram"

    def __init__(self):
        super(telegramBot, self).__init__()
        self.logger = logging.getLogger("notification.telegram")
        self.token = None
        self.token_configuration()

    def token_configuration(self):
        try:
            token = Config.TELEGRAM_BOT_TOKEN
        except AttributeError:
            raise AttributeError(
                "Cannot find 'TELEGRAM_BOT_TOKEN' in the config. " +
                "Please provide it to use telegram notification")
        self.token = token

    @staticmethod
    def get_telegram_chat_ids(user_ids):
        chat_ids = []
        for recipient_id in user_ids:
            try:
                chat_id = (db.session.query(User)
                           .filter_by(id=recipient_id).one()
                           .telegram_chat_id)
            except NoResultFound:  # If manually enter an incorrect user id
                pass
            else:
                chat_ids.append(chat_id)
        db.close_scope()
        return chat_ids

    def send_message(self, message=None, recipients_id=[], retry=5):
        final_ack = {"delivered": [],
                     "failed_delivery": [],
                     }

        if not message:
            self.format_message()
            message = self.message

        if recipients_id:
            send_list = self.get_telegram_chat_ids(recipients_id)
        else:
            recipients_id = self.get_notification_recipients_id()
            send_list = self.get_telegram_chat_ids(recipients_id)

        count = 0
        while True:
            to_send = send_list
            for chat_id in to_send:
                sent_msg = (f"https://api.telegram.org/bot{self.token}" +
                            f"/sendMessage?chat_id={chat_id}&parse_mode=Markdown" +
                            f"&text={message}")
                response = requests.get(sent_msg).json()
                print(response)
                user_ids = (
                    db.session.query(User).filter_by(telegram_chat_id=chat_id)
                    .with_entities(User.id, User.username).one())
                if response["ok"]:
                    final_ack["delivered"].append(user_ids)
                    send_list.remove(chat_id)
                    if user_ids in final_ack["failed_delivery"]:
                        final_ack["failed_delivery"].remove(user_ids)
                else:
                    final_ack["failed_delivery"].append(user_ids)
            if len(send_list) == 0:
                break
            count += 1
            if count == retry:
                break
            sleep(5)
        db.close_scope()
        return f"Message '{message}' final status: {final_ack}"


telegram = telegramBot()
x = telegram.get_notification_recipients_id()

notification_means = [telegram]

summarized_data = {"B612": {"temperature": 18, "humidity": 56, "light": 17895},
                   "Kalahari": {"temperature": 25, "humidity": 46}}

digested_weather = {"morning": 11, "afternoon": 14, "night": 5,
                    "summary": "mostly sunny"}

digested_warnings = "Great, you have no warnings"


@scheduler.scheduled_job(id="daily_recap", trigger="cron",
                         hour=Config.RECAP_SENDING_HOUR,
                         misfire_grace_time=1 * 60)
def send_daily_recap():
    # summarized_data = baseNotification.summarize_data()

    recap_message = baseNotification.create_recap_message(
        summarized_data, digested_weather, digested_warnings)
    print(recap_message)
    for notif_mean in notification_means:
        notif_mean.send_message(recap_message)
