from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext,\
    MessageHandler, Filters

from src.app import API
from src.app.models import User, Role, Permission
from src.services.shared_resources import db
from src.services.template import serviceTemplate


class telegramChatbot(serviceTemplate):
    NAME = "telegram_chatbot"
    LEVEL = "user"

    def _init(self):
        self.updater = None
        self.dispatcher = None

    def get_firstname(self, chat_id):
        with db.scoped_session() as session:
            user = (session.query(User)
                          .filter_by(telegram_chat_id=chat_id)
                          .first())
        if user:
            return user.firstname
        return ""

    def get_role(self, chat_id):
        with db.scoped_session() as session:
            user = (session.query(User)
                    .filter_by(telegram_chat_id=chat_id)
                    .first())
            if user:
                return user.role

            default_role = (session.query(Role)
                            .filter_by(default=True)
                            .first())
            return default_role

    def user_can(self, chat_id, permission):
        role = self.get_role(chat_id)
        return role.has_permission(permission)

    def on_start(self, update: Update, context: CallbackContext) -> None:
        chat_id = update.effective_chat.id
        firstname = self.get_firstname(chat_id=chat_id)
        update.message.reply_html(
            f"Hello{firstname}, welcome to GAIA! To see the commands available, "
            f"type /help."
        )

    def on_light_info(self, update: Update, context: CallbackContext) -> None:
        ecosystems = context.args
        with db.scoped_session() as session:
            message = API.messages.light_info(*ecosystems, session=session)
        update.message.reply_text(message)

    def on_weather(self, update: Update, context: CallbackContext) -> None:
        args = context.args
        if "forecast" in args:
            forecast = True
        else:
            forecast = False
        update.message.reply_text(
            API.messages.weather(forecast=forecast)
        )

    def on_sensors(self, update: Update, context: CallbackContext):
        ecosystems = context.args
        with db.scoped_session() as session:
            message = API.messages.current_sensors_info(
                *ecosystems, session=session)
        update.message.reply_text(message)

    def on_sensors_recap(self, update: Update, context: CallbackContext):
        args = context.args
        to_remove = None
        days = 1
        for arg in args:
            if "day" in arg:
                to_remove = arg
                days = int("".join(i for i in arg if i.isdigit()))
                break
        if days > 5:
            days = 5
        if to_remove:
            args.remove(to_remove)
        ecosystems = args
        with db.scoped_session() as session:
            message = API.messages.recap_sensors_info(
                *ecosystems, session=session, days_ago=days)
        update.message.reply_text(message)

    def on_turn_lights(self, update: Update, context: CallbackContext) -> None:
        chat_id = update.effective_chat.id

        if self.user_can(chat_id, Permission.OPERATE):
            args = context.args
            if len(args) < 2 or len(args) > 3:
                update.message.reply_text(
                    "You need to provide the ecosystem, the mode and "
                    "optionally a timing"
                )
            else:
                ecosystem = args[0]
                mode = args[1]
                if mode not in ("on", "off", "auto", "automatic"):
                    update.message.reply_text(
                        "Mode has to be 'on', 'off' or 'automatic'"
                    )
                if mode == "auto":
                    mode = "automatic"
                if len(args) == 3:
                    countdown = args[2]
                else:
                    countdown = 0
                with db.scoped_session() as session:
                    ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
                        session=session, ecosystems=(ecosystem, ))
                    lights = API.ecosystems.get_light_info(ecosystem_qo)
                    if lights:
                        try:
                            ecosystem_id = API.ecosystems.get_ecosystem_ids(
                                session=session, ecosystem=ecosystem).uid
                        except ValueError:
                            update.message.reply_text(
                                f"Ecosystem {ecosystem} either does not exist"
                            )
                        data = {"ecosystem": ecosystem_id,
                                "actuator": "light",
                                "mode": mode,
                                "countdown": countdown}
                        self.manager.dispatcher.emit("application",
                                                     "turn_actuator",
                                                     data=data)
                        update.message.reply_text(
                            f"Lights have been turn to mode {mode} in {ecosystem}"
                        )
                    else:
                        update.message.reply_text(
                            f"Ecosystem {ecosystem} either does not exist or has "
                            f"no light"
                        )
        else:
            update.message.reply_text("You are not allowed to turn lights on "
                                      "or off")


    def on_recap(self, update: Update, context: CallbackContext) -> None:
        pass

    def base_of_tree(self, update: Update, context: CallbackContext) -> None:
        chat_id = update.effective_chat.id
        firstname = self.get_firstname(chat_id=chat_id)
        # TODO: finish this with a tree of decision

    def on_help(self, update: Update, context: CallbackContext) -> None:
        message = "Here is a list of the commands available:\n"
        message += "/weather : provides the current weather by default and the " \
                   "weather forecast if 'forecast' is provided as an argument.\n"
        message += "/light_info : provides the all the light info for all the" \
                   "ecosystems, or the specified one(s).\n"
        message += "/sensors : provides the current sensors data for all the " \
                   "ecosystems by default, or the specified one(s).\n"
        message += "/sensors_recap : provides the sensors data for the last day" \
                   "for all the ecosystems by default. The number of days " \
                   "covered can be specified by adding '#days' as an argument.\n"
        message += "/recap : send a recap with sensors data of the last 24h, " \
                   "weather forecast, warnings and calendar events.\n"
        update.message.reply_text(message)

    def unknown_command(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        firstname = self.get_firstname(chat_id=chat_id)
        update.message.reply_text(
            f"Sorry {firstname} I did not understand that command. Use /help "
            f"to see the commands available"
        )

    # Put in dummy class
    def _start(self):
        self.updater = Updater(self.config.TELEGRAM_BOT_TOKEN, use_context=True)
        self.dispatcher = self.updater.dispatcher
        for key in dir(self):
            if key.startswith("on_"):
                callback = getattr(self, key)
                self.dispatcher.add_handler(CommandHandler(key[3:], callback))
        # Keep this handler last, it will catch all non recognized commands
        self.dispatcher.add_handler(
            MessageHandler(Filters.command, self.unknown_command))
        self.updater.start_polling()

    def _stop(self):
        self.updater.stop()
        self.dispatcher = None
        self.updater = None
