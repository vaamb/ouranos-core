from telegram import Update
from telegram.ext import (
    filters, MessageHandler, ApplicationBuilder, CommandHandler,
    CallbackContext
)

from src.chat_bot.auth import activate_user, get_current_user
from src.chat_bot.decorators import activation_required
from config import Config
from src.core import api, db
from src.core.g import app_config
from src.core.utils import Tokenizer, ExpiredTokenError, InvalidToken


TELEGRAM_CHAT_ACTIVATION_SUB = "activate_telegram_chat"


async def start(update: Update, context: CallbackContext) -> None:
    telegram_id = update.effective_chat.id
    async with db.scoped_session() as session:
        user = await get_current_user(session, telegram_id)
    if user.is_authenticated:
        greetings = f"Hi {user.firstname}"
    else:
        greetings = "Hello"
    await update.message.reply_html(
        f"{greetings}, welcome to GAIA! To see the commands available, "
        f"type /help."
    )


async def activate(
        update: Update,
        context: CallbackContext,
) -> None:
    telegram_id = update.effective_chat.id
    args = context.args
    if len(args) != 1:
        await update.message.reply_html(
            "You need to provide your activation token after the command"
        )
    token = args[0]
    try:
        payload = Tokenizer.loads(token)
        user_id: str = payload["user_id"]
        sub: str = payload["sub"]
        if sub != TELEGRAM_CHAT_ACTIVATION_SUB:
            raise InvalidToken
        async with db.scoped_session() as session:
            user = await api.user.get(session, user_id)
            if not user:
                await update.message.reply_html(
                    "No user linked to this token was found"
                )
                return
            await activate_user(session, user, telegram_id)
            await update.message.reply_html(
                f"Hi {user.username}. You are now allowed to fully use the chat "
                f"bot. To see the commands available, type /help "
            )
    except ExpiredTokenError:
        await update.message.reply_html(
            "This token has expired, ask for a new one and repeat the "
            "activation process"
        )
    except (InvalidToken, KeyError):
        await update.message.reply_html(
            "This token is invalid"
        )


@activation_required
async def ecosystem_status(
        update: Update,
        context: CallbackContext,
) -> None:
    ecosystems = context.args
    async with db.scoped_session() as session:
        msg = await api.messages.ecosystem_summary(session, ecosystems)
    await update.message.reply_html(msg)


@activation_required
async def sensors(
        update: Update,
        context: CallbackContext,
) -> None:
    ecosystems_name = context.args
    async with db.scoped_session() as session:
        ecosystems = await api.ecosystem.get_multiple(session, ecosystems_name)
        data = [
            api.sensor.get_current_data(ecosystem.uid)
            .update({"ecosystem_name": ecosystem.name})
            for ecosystem in ecosystems
        ]
    await update.message.reply_html("data")


@activation_required
def light_info(
        update: Update,
        context: CallbackContext,
) -> None:
    ecosystems_name = context.args
    async with db.scoped_session() as session:
        ecosystems = await api.ecosystem.get_multiple(session, ecosystems_name)
        data = [
            api.ecosystem.get_light_info(ecosystem) for ecosystem in ecosystems
        ]
    await update.message.reply_text("data")


"""
def on_weather(self, update, context) -> None:
    args = context.args
    if "forecast" in args:
        forecast = True
    else:
        forecast = False
    update.message.reply_text(
        api.messages.weather(forecast=forecast)
    )

def on_sensors_recap(self, update, context):
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

def on_turn_lights(self, update, context) -> None:
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
                ecosystem_qo = api.ecosystem.get_multiple(
                    session=session, ecosystems=(ecosystem, ))
                lights = api.ecosystem.get_light_info(ecosystem_qo)
                if lights:
                    try:
                        ecosystem_id = api.ecosystem.get_ids(
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


def base_of_tree(self, update, context) -> None:
    chat_id = update.effective_chat.id
    firstname = self.get_firstname(chat_id=chat_id)
    # TODO: finish this with a tree of decision
"""


async def help_cmd(update: Update, context: CallbackContext) -> None:
    telegram_id = update.effective_chat.id
    async with db.scoped_session() as session:
        user = await get_current_user(session, telegram_id)
    msg = "Here is a list of the commands available:\n"
    if user.is_anonymous:
        msg += "/register : register using the token received on the website " \
               "or by email.\n"
        await update.message.reply_html(msg)
        return
    msg += "/ecosystem_status : provides the status of all the ecosystems by " \
           "default or the specifies ones.\n"
    msg += "/weather : provides the current weather by default and the weather " \
           "forecast if 'forecast' is provided as an argument.\n"
    msg += "/light_info : provides the all the light info for all the " \
           "ecosystems, or the specified one(s).\n"
    msg += "/sensors : provides the current sensors data for all the ecosystems " \
           "by default, or the specified one(s).\n"
    msg += "/sensors_recap : provides the summary of the sensors data for the " \
           "last day for all the ecosystems by default. The number of days " \
           "covered can be specified by adding '#days' as an argument.\n"
    msg += "/recap : send a recap with sensors data of the last 24h, weather " \
           "forecast, warnings and calendar socketio.\n"
    await update.message.reply_text(msg)


async def unknown_command(update: Update, context: CallbackContext):
    telegram_id = update.effective_chat.id
    async with db.scoped_session() as session:
        user = await get_current_user(session, telegram_id)
    if user.is_authenticated:
        sorry = f"Sorry {user.username},"
    else:
        sorry = "Sorry,"
    await update.message.reply_text(
        f"{sorry} I did not understand that command. Use /help to see the "
        f"commands available"
    )


class ChatBot:
    def __init__(self):
        if not app_config.get("TELEGRAM_BOT_TOKEN"):
            raise RuntimeError(
                "The config key 'TELEGRAM_BOT_TOKEN' needs to be set in order "
                "to use the chatbot"
            )
        application = ApplicationBuilder()
        application.token(app_config["TELEGRAM_BOT_TOKEN"])
        self.application = application.build()

    def load_handlers(self):
        start_handler = CommandHandler('start', start)
        self.application.add_handler(start_handler)

        ecosystem_status_handler = CommandHandler('ecosystem_status', ecosystem_status)
        self.application.add_handler(ecosystem_status_handler)

        help_handler = CommandHandler("help", help_cmd)
        self.application.add_handler(help_handler)

        unknown_command_handler = MessageHandler(filters.COMMAND, unknown_command)
        self.application.add_handler(unknown_command_handler)

    def start(self):
        self.application.run_polling()


if __name__ == '__main__':
    db.init(Config)
    chat_bot = ChatBot()
    chat_bot.load_handlers()
    chat_bot.start()
