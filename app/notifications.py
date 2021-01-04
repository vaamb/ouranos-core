from datetime import date, datetime, time, timedelta
import logging
from statistics import mean, mode
from time import sleep

import requests
from sqlalchemy.orm.exc import NoResultFound

from app import app_name, scheduler
import app.API as API
from app.database import out_of_Flask_data_db as db
from app.models import User
from config import Config

base_logger = logging.getLogger(f"{app_name}.notification")


class Notification:
    @staticmethod
    def get_notification_recipients_id():
        recipients_id = []
        with db.scoped_session() as session:
            recipients = session.query(User).filter(
                User.daily_recap.is_(True)).all()
            for recipient in recipients:
                recipients_id.append(recipient.id)
        return recipients_id


class telegramBot:
    METHOD = "Telegram"

    def __init__(self):
        super(telegramBot, self).__init__()
        self.logger = logging.getLogger(f"{base_logger.name}.telegram")
        self.logger.info("Starting telegram bot")
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
        with db.scoped_session() as session:
            for recipient_id in user_ids:
                try:
                    chat_id = (session.query(User)
                               .filter_by(id=recipient_id).one()
                               .telegram_chat_id)
                except NoResultFound:  # If manually enter an incorrect user id
                    pass
                else:
                    chat_ids.append(chat_id)
        return chat_ids

    def send_message(self, message, recipients_id=[], retry=5):
        self.logger.debug("Sending message")
        final_ack = {"delivered": [],
                     "failed_delivery": [],
                     }
        if recipients_id:
            send_list = self.get_telegram_chat_ids(recipients_id)
        else:
            recipients_id = Notification.get_notification_recipients_id()
            send_list = self.get_telegram_chat_ids(recipients_id)

        count = 0
        with db.scoped_session() as session:
            while True:
                to_send = send_list
                for chat_id in to_send:
                    sent_msg = (f"https://api.telegram.org/bot{self.token}" +
                                f"/sendMessage?chat_id={chat_id}&parse_mode=Markdown" +
                                f"&text={message}")
                    response = requests.get(sent_msg).json()
                    user_name = (
                        session.query(User).filter_by(telegram_chat_id=chat_id)
                            .one().username)
                    if response["ok"]:
                        final_ack["delivered"].append(user_name)
                        send_list.remove(chat_id)
                        if user_name in final_ack["failed_delivery"]:
                            final_ack["failed_delivery"].remove(user_name)
                    else:
                        final_ack["failed_delivery"].append(user_name)
                if len(send_list) == 0:
                    break
                count += 1
                if count == retry:
                    break
                sleep(5)
        return {"message": message, "status": final_ack}


telegram = telegramBot()

notification_means = [telegram]


@scheduler.scheduled_job(id="daily_recap", trigger="cron",
                         hour=Config.RECAP_SENDING_HOUR,
                         misfire_grace_time=30 * 60)
def send_daily_recap():
    start = datetime.combine(date.today() - timedelta(days=1), time())
    stop = datetime.combine(date.today(), time())
    recap_message = API.get_recap_message(
        start, stop, ecosystem_message_base="Yesterday sensors average:\n")

    base_logger.debug(f"Sending recap message: '''\n{recap_message}\n'''")

    for notif_mean in notification_means:
        response = notif_mean.send_message(recap_message)
        notif_mean.logger.debug(f"{response['status']}")
