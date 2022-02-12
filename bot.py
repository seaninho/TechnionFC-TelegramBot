import logging

from telegram import TelegramError
from telegram.ext import Updater, CommandHandler

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_GROUP_INVITE_LINK, PORT

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)

logger = logging.getLogger(__name__)


def start_command(update, context):
    """Send bot welcome message"""
    user = update.message.from_user
    message = 'TechnionFC Bot has started operating\.\.\.\n\nPlease use the /help command to list your options'

    user.send_message(message, parse_mode='MarkdownV2')


def is_group_member(update, context, user):
    """Check if user is a group member"""
    user_is_group_member = True
    try:
        chat_member = context.bot.get_chat_member(TELEGRAM_CHAT_ID, user.id)
        if chat_member.status in ('left', 'kicked'):
            user_is_group_member = False
            update.message.reply_text(f'Hi {user.full_name},\n'
                                      f'you are not a part of the Technion FC group anymore...\n\n'
                                      f'To rejoin our group, please use {TELEGRAM_GROUP_INVITE_LINK}')
    except TelegramError:
        user_is_group_member = False
        update.message.reply_text(f'Hi {user.full_name},\n'
                                  f'you are not a part of the Technion FC group...\n\n'
                                  f'To join our group, please use {TELEGRAM_GROUP_INVITE_LINK}')
    finally:
        return user_is_group_member


def get_command_in_public_warning(user, command):
    """Return a warning message for users who publicly send a command that should be sent in private"""
    return f'Hi {user.first_name},\n'\
           f'Please send the /{command} command using the bot\'s private chat @ https://t.me/FCTechnionBot.\n\n'\
           f'If you have any questions, feel free to ask :)'


def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main():
    """The official Technion FC Telegram bot"""

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True, request_kwargs={'read_timeout': 60, 'connect_timeout': 60})

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # on different commands - answer in Telegram
    dp.add_handler(CommandHandler("start", start_command, pass_job_queue=True))

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    # updater.start_polling()
    updater.start_webhook(listen="0.0.0.0",
                          port=int(PORT),
                          url_path=TELEGRAM_BOT_TOKEN,
                          webhook_url='https://technionfc-telegram-bot.herokuapp.com/' + TELEGRAM_BOT_TOKEN)

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    main()
