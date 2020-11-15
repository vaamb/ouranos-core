from datetime import date, datetime, time, timedelta
import logging
from statistics import mean, mode, StatisticsError
from time import sleep

import requests
from sqlalchemy.orm.exc import NoResultFound

from app import app_name, scheduler
from app.database import out_of_Flask_db as db
from app.dataspace import Outside
from app.models import Data, Ecosystem, Hardware, User
from config import Config


base_logger = logging.getLogger(f"{app_name}.notification")


class Notification:
    summary_sep = "=================================\n"
    ecosystem_summary_sep = "---------------------------------\n"

    @staticmethod
    def get_notification_recipients_id():
        recipients_id = []
        with db.scoped_session() as session:
            recipients = session.query(User).filter(
                User.notifications.is_(True)).all()
            for recipient in recipients:
                recipients_id.append(recipient.id)
        return recipients_id

    @staticmethod
    def get_ecosystem_measures_mean(db_session,
                                    level,
                                    ecosystem_uid,
                                    time_window=("start", "now")):

        time_window_a = (time_window[0] if time_window[0] != "start"
                         else datetime.fromtimestamp(0))
        time_window_p = (time_window[1] if time_window[1] != "now"
                         else datetime.now())
        result = {}

        measures = [d.measure for d in
                    (db_session.query(Data).join(Hardware)
                     .filter(Data.ecosystem_id == ecosystem_uid)
                     .filter(Hardware.level == level)
                     .filter(time_window_a < Data.datetime)
                     .filter(Data.datetime <= time_window_p)
                     .group_by(Data.measure)
                     .all())]

        for measure in measures:
            result[measure] = {}
            _data = (db_session.query(Data).join(Hardware)
                     .filter(Data.ecosystem_id == ecosystem_uid)
                     .filter(Hardware.level == level)
                     .filter(Data.measure == measure)
                     .filter(time_window_a < Data.datetime)
                     .filter(Data.datetime <= time_window_p)
                     .with_entities(Data.datetime, Data.value)
                     .all())
            data = round(mean([i[1] for i in _data]), 2)
            result[measure] = data
        return result

    @staticmethod
    def get_measures_summary(time_window):
        measures_summary = {}
        with db.scoped_session() as session:
            ecosystem_ids = (session.query(Ecosystem)
                             .filter_by(status=1)
                             .with_entities(Ecosystem.id, Ecosystem.name)
                             .all())
            for ecosystem_id in ecosystem_ids:
                summary = (Notification
                           .get_ecosystem_measures_mean(db_session=session,
                                                        level="environment",
                                                        ecosystem_uid=
                                                        ecosystem_id[0],
                                                        time_window=time_window))
                if summary:
                    measures_summary[ecosystem_id[1]] = summary
        return measures_summary

    # TODO: make it work with a time window, not only at 5 in the morning
    @staticmethod
    def digest_weather_data(weather_data):
        morning = {"data": []}
        afternoon = {"data": []}
        night = {"data": []}
        summary = {"data": []}
        for hour in weather_data["hourly"]:
            dt = datetime.fromtimestamp(hour["time"])
            if (datetime.combine(date.today(), time(6)) <=
                    dt <
                    datetime.combine(date.today(), time(12))):
                morning["data"].append(hour["temperature"])
                summary["data"].append(hour["summary"])
            elif (datetime.combine(date.today(), time(12)) <=
                  dt <
                  datetime.combine(date.today(), time(20))):
                afternoon["data"].append(hour["temperature"])
                summary["data"].append(hour["summary"])
            elif (datetime.combine(date.today(), time(20)) <=
                  dt <
                  datetime.combine((date.today() + timedelta(days=1)),
                                   time(20))):
                night["data"].append(hour["temperature"])
        for moment in [morning, afternoon, night]:
            try:
                moment["mean"] = round(mean(moment["data"]), 1)
            except StatisticsError:
                moment["mean"] = None
        try:
            summary["mode"] = mode(summary["data"])
        except StatisticsError:
            summary["mode"] = None
        results = {"morning": morning["mean"],
                   "afternoon": afternoon["mean"],
                   "night": night["mean"],
                   "summary": summary["mode"]
                   }
        return results

    # TODO: digest warnings
    @staticmethod
    def digest_warnings(warnings={}):
        return warnings

    @staticmethod
    def format_ecosystem_recap(summarized_measures):
        measure_unit = {"absolute_humidity": "g/m³",
                        "dew_temperature": "°C",
                        "temperature": "°C",
                        "humidity": "% hum",
                        "light": "lux"}
        if not summarized_measures:
            return ""
        ecosystems_summary = "Yesterday sensors average:\n"
        for i, ecosystem in enumerate(summarized_measures):
            indent = (len(ecosystem)) * " "
            for j, measure in enumerate(summarized_measures[ecosystem]):
                unit = measure_unit.get(measure, "")
                if j == 0:
                    left = ecosystem
                else:
                    left = indent
                ecosystems_summary += \
                    (f"{left} - {measure}: ".replace("_", " ") +
                     f"{summarized_measures[ecosystem][measure]}{unit}\n")
            if i < len(summarized_measures) - 1:
                ecosystems_summary += Notification.ecosystem_summary_sep
        ecosystems_summary += Notification.summary_sep
        return ecosystems_summary

    # TODO: add a summary for day and night
    @staticmethod
    def format_weather_forecast(digested_weather):
        message = ""
        before = False
        if (digested_weather["morning"] or
                digested_weather["morning"] or
                digested_weather["night"]):
            message += "Today's weather will be "
            if digested_weather["morning"]:
                message += f"{digested_weather['morning']}°C in the morning"
                before = True
            if digested_weather["afternoon"]:
                if before:
                    message += ", "
                message += f"{digested_weather['afternoon']}°C in the afternoon"
                before = True
            if digested_weather["night"]:
                if before:
                    message += " and "
                message += f"{digested_weather['night']}°C in the night"
            message += ". "
        if digested_weather["summary"]:
            message += f"It will be {digested_weather['summary'].lower()}."
        if message:
            message += f"\n{Notification.summary_sep}"
        return message

    # TODO format warnings message
    @staticmethod
    def format_warnings_recap(digested_warnings):
        if not digested_warnings:
            return f"Great, you have no warnings.\n{Notification.summary_sep}"

    @staticmethod
    def format_recap_message(ecosystem_recap, weather_forecast,
                             warnings_recap):
        today = datetime.now().strftime("%A %d %B")
        calendar_message = f"Don't forget to water and feed your plants.\n{Notification.summary_sep}"
        message = f"GAIA daily recap for {today}\n{Notification.summary_sep}"
        message += ecosystem_recap
        message += weather_forecast
        message += warnings_recap
        message += calendar_message
        message += "Have a nice day!"
        return message


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
                         misfire_grace_time=30*60)
def send_daily_recap():
    start = datetime.combine(date.today() - timedelta(days=1), time())
    stop = datetime.combine(date.today(), time())
    measures_summary = Notification.get_measures_summary(
        time_window=(start, stop))
    ecosystem_recap = Notification.format_ecosystem_recap(measures_summary)

    digested_weather = Notification.digest_weather_data(Outside.weather_data)
    weather_forecast = Notification.format_weather_forecast(digested_weather)

    digested_warnings = Notification.digest_warnings()
    warnings_recap = Notification.format_warnings_recap(digested_warnings)

    recap_message = Notification.format_recap_message(
        ecosystem_recap, weather_forecast, warnings_recap)

    base_logger.debug(f"Sending recap message: '''\n{recap_message}\n'''")
    for notif_mean in notification_means:
        response = notif_mean.send_message(recap_message)
        notif_mean.logger.debug(response["status"])
