import asyncio

from telegram import Update
from telegram.ext import (
    filters, MessageHandler, ApplicationBuilder, CommandHandler,
    CallbackContext
)

from config import Config
from src.core import api, db


token = Config.TELEGRAM_BOT_TOKEN


async def get_firstname(session, telegram_id):
    user = await api.user.get_by_telegram_id(session, telegram_id)
    if user:
        return user.firstname
    return ""


async def start(update: Update, context: CallbackContext) -> None:
    telegram_id = update.effective_chat.id
    async with db.scoped_session() as session:
        firstname = await get_firstname(session, telegram_id=telegram_id)
    if firstname:
        greetings = f"Hi {firstname}"
    else:
        greetings = "Hello"
    await update.message.reply_html(
        f"{greetings}, welcome to GAIA! To see the commands available, "
        f"type /help."
    )


async def ecosystem_status(update: Update, context: CallbackContext) -> None:
    args = context.args
    async with db.scoped_session() as session:
        msg = await api.messages.ecosystem_summary(session, args)
    await update.message.reply_html(msg)


"""
def on_light_info(self, update, context) -> None:
    ecosystems = context.args
    with db.scoped_session() as session:
        message = api.messages.light_info(*ecosystems, session=session)
    update.message.reply_text(message)



def on_weather(self, update, context) -> None:
    args = context.args
    if "forecast" in args:
        forecast = True
    else:
        forecast = False
    update.message.reply_text(
        api.messages.weather(forecast=forecast)
    )

def on_sensors(self, update, context):
    ecosystems = context.args
    with db.scoped_session() as session:
        message = api.messages.current_sensors_info(
            *ecosystems, session=session)
    update.message.reply_text(message)

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


def on_recap(self, update, context) -> None:
    pass

def base_of_tree(self, update, context) -> None:
    chat_id = update.effective_chat.id
    firstname = self.get_firstname(chat_id=chat_id)
    # TODO: finish this with a tree of decision

def on_help(self, update, context) -> None:
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
               "weather forecast, warnings and calendar socketio.\n"
    update.message.reply_text(message)

def unknown_command(self, update, context):
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
"""

if __name__ == '__main__':
    db.init(Config)

    application = ApplicationBuilder().token(token).build()

    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    ecosystem_status_handler = CommandHandler('ecosystem_status', ecosystem_status)
    application.add_handler(ecosystem_status_handler)

    application.run_polling()
