import logging

from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext,\
    MessageHandler, Filters

from app import API
from config import Config
from app.database import out_of_Flask_users_db as db
from app.models import User


logger = logging.getLogger("service.telegram")
updater = None


def get_user_firstname(chat_id):
    with db.scoped_session() as session:
        firstname = (session.query(User)
                     .filter_by(telegram_chat_id=chat_id)
                     .first()
                     .firstname)
    if firstname:
        return firstname.rjust(len(firstname) + 1)
    return ""


def get_user_permission(chat_id, permission):
    with db.scoped_session() as session:
        user = (session.query(User)
                .filter_by(telegram_chat_id=chat_id)
                .first())
    if user:
        return user.can(permission)
    return False


def welcome(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    firstname = get_user_firstname(chat_id=chat_id)
    update.message.reply_text(
        f"Hello{firstname}, welcome to GAIA! To see the commands available, type "
        f"/help."
    )


def get_light_info(update: Update, context: CallbackContext) -> None:
    args = context.args
    ecosystem_uids = API.get_listed_ecosystems(args)
    info = 1
    for ecosystem_uid in ecosystem_uids:
        API.get_ecosystem_light_info(ecosystem_uid)
    update.message.reply_text(

    )


def get_info(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    firstname = get_user_firstname(chat_id=chat_id)
    # TODO: finish this with a tree of decision


def get_weather(update: Update, context: CallbackContext) -> None:
    args = context.args
    if "forecast" in args:
        weather_forecast = API.get_weather_forecast()
        digested_weather = API.digest_weather_forecast(weather_forecast)
        summarized_weather = API.summarize_weather_forecast(digested_weather)
        message = API.format_weather_forecast(summarized_weather)
        update.message.reply_text(message)
        return
    current_weather = API.get_current_weather()
    message = API.format_current_weather(current_weather)
    update.message.reply_text(message)
    return


def get_recap(update: Update, context: CallbackContext) -> None:
    message = API.get_recap_message()
    update.message.reply_text(message)


def get_current_data(update: Update, context: CallbackContext) -> None:
    args = context.args
    message = API.Messages.current_data(ecosystem_names=args)
    update.message.reply_text(message)


def help(update: Update, context: CallbackContext) -> None:
    message = "Here is a list of the commands available:\n"
    message += "/weather : provides the current weather by default or the " \
               "weather forecast if 'forecast' is provided as an argument.\n"
    message += "/recap : send a recap with sensors data of the last 24h, " \
               "weather forecast, warnings and calendar events.\n"
    message += "/current_data : provides the current sensors data for all the " \
               "ecosystems by default, or the specified one(s)."
    update.message.reply_text(message)


def unknown_command(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    firstname = get_user_firstname(chat_id=chat_id)
    update.message.reply_text(
        f"Sorry{firstname}, I did not understand that command. Use /help to see"
        f"commands available"
    )


def start():
    global updater
    if not updater:
        updater = Updater(Config.TELEGRAM_BOT_TOKEN, use_context=True)
        dispatcher = updater.dispatcher

        dispatcher.add_handler(CommandHandler("start", welcome))
        dispatcher.add_handler(CommandHandler("get_info", get_info))
        dispatcher.add_handler(CommandHandler("current_data", get_current_data))
        dispatcher.add_handler(CommandHandler("weather", get_weather))
        dispatcher.add_handler(CommandHandler("recap", get_recap))
        dispatcher.add_handler(CommandHandler("help", help))
        # Keep this handler last, it will catch all non recognized commands
        dispatcher.add_handler(MessageHandler(Filters.command, unknown_command))

        updater.start_polling()


def stop():
    global updater
    if updater:
        updater.stop()
        updater = None
