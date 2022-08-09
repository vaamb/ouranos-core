try:
    import telegram
except ImportError:
    telegram = None

from src import api
from src.database.models.app import User, Role, Permission
from src.services.shared_resources import db
from src.services.template import ServiceTemplate


class TelegramChatBot(ServiceTemplate):
    LEVEL = "user"

    def __init__(self, *args, **kwargs):
        if not telegram:
            raise RuntimeError(
                "python-telegram-bot package is required. Run "
                "`pip install python-telegram-bot` in your virtual env."
            )
        super().__init__(*args, **kwargs)
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

    def on_start(self, update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
        chat_id = update.effective_chat.id
        firstname = self.get_firstname(chat_id=chat_id)
        update.message.reply_html(
            f"Hello{firstname}, welcome to GAIA! To see the commands available, "
            f"type /help."
        )

    def on_light_info(self, update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
        ecosystems = context.args
        with db.scoped_session() as session:
            message = api.messages.light_info(*ecosystems, session=session)
        update.message.reply_text(message)

    def on_weather(self, update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
        args = context.args
        if "forecast" in args:
            forecast = True
        else:
            forecast = False
        update.message.reply_text(
            api.messages.weather(forecast=forecast)
        )

    def on_sensors(self, update: telegram.Update, context: telegram.ext.CallbackContext):
        ecosystems = context.args
        with db.scoped_session() as session:
            message = api.messages.current_sensors_info(
                *ecosystems, session=session)
        update.message.reply_text(message)

    def on_sensors_recap(self, update: telegram.Update, context: telegram.ext.CallbackContext):
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
            message = api.messages.recap_sensors_info(
                *ecosystems, session=session, days_ago=days)
        update.message.reply_text(message)

    def on_turn_lights(self, update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
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
                    ecosystem_qo = api.gaia.get_ecosystems(
                        session=session, ecosystems=(ecosystem, ))
                    lights = api.gaia.get_light_info(ecosystem_qo)
                    if lights:
                        try:
                            ecosystem_id = api.gaia.get_ecosystem_ids(
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


    def on_recap(self, update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
        pass

    def base_of_tree(self, update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
        chat_id = update.effective_chat.id
        firstname = self.get_firstname(chat_id=chat_id)
        # TODO: finish this with a tree of decision

    def on_help(self, update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
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

    def unknown_command(self, update: telegram.Update, context: telegram.ext.CallbackContext):
        chat_id = update.effective_chat.id
        firstname = self.get_firstname(chat_id=chat_id)
        update.message.reply_text(
            f"Sorry {firstname} I did not understand that command. Use /help "
            f"to see the commands available"
        )

    # Put in dummy class
    def _start(self):
        self.updater = telegram.ext.Updater(self.config.TELEGRAM_BOT_TOKEN, use_context=True)
        self.dispatcher = self.updater.dispatcher
        for key in dir(self):
            if key.startswith("on_"):
                callback = getattr(self, key)
                self.dispatcher.add_handler(telegram.ext.CommandHandler(key[3:], callback))
        # Keep this handler last, it will catch all non recognized commands
        self.dispatcher.add_handler(
            telegram.ext.MessageHandler(telegram.ext.Filters.command, self.unknown_command))
        self.updater.start_polling()

    def _stop(self):
        self.updater.stop()
        self.dispatcher = None
        self.updater = None
