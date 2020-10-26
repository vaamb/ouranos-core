# -*- coding: utf-8 -*-
import logging
from time import sleep
from datetime import datetime, timezone, timedelta

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound

from config import Config
from app.models import User, Data, Ecosystem, Hardware


base_logger = logging.getLogger("notification")

engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)


class baseNotification:
    @staticmethod
    def get_notification_recipients_id():
        recipients_id = []
        session = Session(engine)
        recipients = session.query(User).filter(User.notifications == True).all()
        for recipient in recipients:
            recipients_id.append(recipient.id)
        session.close()
        return recipients_id

    @staticmethod
    def summarize_data():
        last_24h = datetime.now(timezone.utc) - timedelta(days=1)
        session = Session(engine)
        for ecosystem in session.query(Ecosystem).filter(Ecosystem.status == True):
            #TODO: average the sensors data for last 24h
            #TODO: average weather data
            pass

    @staticmethod
    def create_recap_message(summarized_data):
        #TODO: take averages from summarized data and inject them in the template
        #add spaces before - temperature ... equal to length ecosystem_name + 1
        template = """
GAIA daily recap'
===============================
Yesterday sensors average: 
B612 - temperature: 17.9°C 
   - humidity: 57% 
-------------------------------
Kalahary - blbablabla
===============================
Today's weather will be 11°C in
the morning, 12°C in the afternoon
and 6°C during the night. It will
mostly sunny.
===============================
Don't forget to water and feed
your plants
===============================
Great, you have no warnings
===============================
Have a nice day!
"""
        message = template
        return message


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
            token = None
            raise AttributeError("Cannot find 'TELEGRAM_BOT_TOKEN' in the config. Please " +
                                 "provide it to use telegram notification")
        self.token = token

    @staticmethod
    def get_telegram_chat_ids(user_ids):
        chat_ids = []
        session = Session(engine)
        for recipient_id in user_ids:
            try:
                chat_id = session.query(User).filter_by(id=recipient_id).one().telegram_chat_id
            except NoResultFound:  # If manually enter an incorrect user id
                pass
            else:
                chat_ids.append(chat_id)
        session.close()
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
        session = Session(engine)
        while True:
            to_send = send_list
            for chat_id in to_send:
                sent_msg = (f"https://api.telegram.org/bot{self.token}" +
                            f"/sendMessage?chat_id={chat_id}&parse_mode=Markdown" +
                            f"&text={message}")
                response = requests.get(sent_msg).json()
                user_ids = (session.query(User).filter_by(telegram_chat_id=chat_id)
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
        session.close()
        return f"Message '{message}' final status: {final_ack}"


telegram = telegramBot()
x = telegram.get_notification_recipients_id()

notification_means = [telegram]


def send_daily_recap():
    summarized_data = baseNotification.summarize_data()
    recap_message = baseNotification.create_recap_message(summarized_data)
    for notif_mean in notification_means:
        notif_mean.send_message(recap_message)
