from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext,\
    MessageHandler, Filters

# TODO: with new API: import it in _start() to avoid circular import
#from app import API_old as API
from config import Config
from app.database import out_of_Flask_app_db as db
from app.models import User
from services.template import serviceTemplate


class telegramChatbot(serviceTemplate):
    NAME = "telegram_chatbot"
    LEVEL = "user"

    def _init(self):
        self.updater = None
        self.dispatcher = None

    def get_user_firstname(self, chat_id):
        with db.scoped_session() as session:
            firstname = (session.query(User)
                         .filter_by(telegram_chat_id=chat_id)
                         .first()
                         .firstname)
        if firstname:
            return firstname.rjust(len(firstname) + 1)
        return ""

    def get_user_permission(self, chat_id, permission):
        with db.scoped_session() as session:
            user = (session.query(User)
                    .filter_by(telegram_chat_id=chat_id)
                    .first())
        if user:
            return user.can(permission)
        return False

    def welcome(self, update: Update, context: CallbackContext) -> None:
        chat_id = update.effective_chat.id
        firstname = self.get_user_firstname(chat_id=chat_id)
        update.message.reply_text(
            f"Hello{firstname}, welcome to GAIA! To see the commands available, type "
            f"/help."
        )

    def get_light_info(self, update: Update, context: CallbackContext) -> None:
        args = context.args
        ecosystem_uids = API.get_listed_ecosystems(args)
        # TODO: finish this
        info = {}
        for ecosystem_uid in ecosystem_uids:
            info.update(API.ecosystems.get_ecosystem_light_info(ecosystem_uid))
        update.message.reply_text(info)

    def get_info(self, update: Update, context: CallbackContext) -> None:
        chat_id = update.effective_chat.id
        firstname = self.get_user_firstname(chat_id=chat_id)
        # TODO: finish this with a tree of decision

    def get_weather(self, update: Update, context: CallbackContext) -> None:
        args = context.args
        if "forecast" in args:
            weather_forecast = API.get_weather_forecast()
            digested_weather = API.digest_weather_forecast(weather_forecast)
            summarized_weather = API.summarize_weather_forecast(
                digested_weather)
            message = API.format_weather_forecast(summarized_weather)
            update.message.reply_text(message)
            return
        current_weather = API.get_current_weather()
        message = API.format_current_weather(current_weather)
        update.message.reply_text(message)
        return

    def get_recap(self, update: Update, context: CallbackContext) -> None:
        message = API.Messages.recap()
        update.message.reply_text(message)

    def get_current_data(self, update: Update, context: CallbackContext) -> None:
        args = context.args
        message = API.Messages.current_data(ecosystem_names=args)
        update.message.reply_text(message)

    def help(self, update: Update, context: CallbackContext) -> None:
        message = "Here is a list of the commands available:\n"
        message += "/weather : provides the current weather by default or the " \
                   "weather forecast if 'forecast' is provided as an argument.\n"
        message += "/recap : send a recap with sensors data of the last 24h, " \
                   "weather forecast, warnings and calendar events.\n"
        message += "/current_data : provides the current sensors data for all the " \
                   "ecosystems by default, or the specified one(s)."
        update.message.reply_text(message)

    def unknown_command(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        firstname = self.get_user_firstname(chat_id=chat_id)
        update.message.reply_text(
            f"Sorry{firstname}, I did not understand that command. Use /help to see"
            f"commands available"
        )

    # Put in dummy class
    def _start(self):
        self.updater = Updater(Config.TELEGRAM_BOT_TOKEN, use_context=True)
        self.dispatcher = self.updater.dispatcher
        # TODO: Move in a dict loop
        self.dispatcher.add_handler(CommandHandler("start", self.welcome))
        self.dispatcher.add_handler(CommandHandler("get_info", self.get_info))
        self.dispatcher.add_handler(
            CommandHandler("current_data", self.get_current_data))
        self.dispatcher.add_handler(CommandHandler("weather", self.get_weather))
        self.dispatcher.add_handler(CommandHandler("recap", self.get_recap))
        self.dispatcher.add_handler(CommandHandler("help", self.help))
        # Keep this handler last, it will catch all non recognized commands
        self.dispatcher.add_handler(
            MessageHandler(Filters.command, self.unknown_command))
        self.updater.start_polling()

    def _stop(self):
        self.updater.stop()
        self.dispatcher = None
        self.updater = None
