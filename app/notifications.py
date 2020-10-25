# -*- coding: utf-8 -*-
import logging
from time import sleep
from datetime import datetime

import requests

from config import Config
from app.models import User, Data
from app import scheduler

base_logger = logging.getLogger("notification")


class baseNotification:
    def __init__(self):
        self.recipients_id = []
        self.message = ""

    def get_recipients(self):
        recipients = User.query.filter(User.notifications == True).all()
        for recipient in recipients:
            self.recipients_id.append(recipient.id)

    def summarize_data(self):
        pass

    def format_message(self):
        base_message =  """
GAIA daily recap'
-------------------------------
Yesterday sensors average: 
B612 - temperature: 18.6°C 
   - humidity: 58% 
Kalahary - blbablabla
-------------------------------
Today's weather will be 8°C in
the morning, 14°C in the afternoon
and 5°C during the night.
-------------------------------
Don't forget to water and feed
your plants
-------------------------------
No warnings to display
-------------------------------
Have a nice day!
"""


class telegramBot(baseNotification):
    def __init__(self):
        super(telegramBot, self).__init__()
        self.logger = logging.getLogger("notification.telegram")
        self.token = None
        self.token_configuration()
        self.chat_ids = []

    def token_configuration(self):
        try:
            token = Config.TELEGRAM_BOT_TOKEN
        except AttributeError:
            token = None
            raise AttributeError("Cannot find 'TELEGRAM_BOT_TOKEN' in the config. Please " +
                                 "provide it to use telegram notification")
        self.token = token

    def get_chat_ids(self):
        self.get_recipients()
        for recipient_id in self.recipients_id:
            chat_id = User.query.filter_by(id=recipient_id).one().telegram_chat_id
            if chat_id:
                self.chat_ids.append(chat_id)

    def send_message(self, message=None, retry=5):
        if not message:
            self.format_message()
            message = self.message

        self.get_chat_ids()
        final_ack = {"delivered": [],
                     "failed_delivery": [],
                     }
        send_list = self.chat_ids
        count = 0
        while True:
            to_send = send_list
            for chat_id in to_send:
                sent_msg = (f"https://api.telegram.org/bot{self.token}" +
                            f"/sendMessage?chat_id={chat_id}&parse_mode=Markdown" +
                            f"&text={message}")
                response = requests.get(sent_msg).json()
                user_ids = (User.query.filter_by(telegram_chat_id=chat_id)
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
        return(f"Message '{message}' final status: {final_ack}")

x = telegramBot()

scheduler.add_job(func=x.send_message, args=("Without flask sqlalchemy",),
                                trigger="cron", minute="*", misfire_grace_time=5*60,
                                id="err")

