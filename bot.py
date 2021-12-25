import logging

from telegram import TelegramError
from telegram.ext import Updater, CommandHandler

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_GROUP_INVITE_LINK, PORT

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)

logger = logging.getLogger(__name__)

# Emojis
OK_SIGN_EMOJI_CODE = '\U0001F44C'


def start_command(update, context):
    """Send bot welcome message"""
    user = update.message.from_user
    message = 'TechnionFC Bot has started operating\.\.\.\n\nPlease use the /help command to list your options'

    user.send_message(message, parse_mode='MarkdownV2')


def help_command(update, context):
    """Send bot help message"""
    user = update.message.from_user
    if str(update.message.chat.id) == TELEGRAM_CHAT_ID:
        return update.message.reply_text(get_command_in_public_warning(user, 'help'))

    message = f'Welcome to the *Technion Football Club*\!\n\n'\
              f'This bot\'s purpose is to ease the players\' registration process {OK_SIGN_EMOJI_CODE}\n' \
              f'\n*Club rules* :\n' \
              f'0\. Club matchdays are: _Monday @ 20:30\-22:30, Thursday @ 20:00\-22:00_\n' \
              f'If you can not attend the FULL 2 hours, please refrain from adding yourself to the list\.\n\n' \
              f'1\. Players MUST use their full names in their telegram profiles \(Hebrew or English\)\.\n' \
              f'NO SPECIAL CHARACTERS ALLOWED\!\!\!\n\n' \
              f'2\. Players must be either Technion students \(or married to one\) or \n' \
              f'Technion Pre\-Academic Prep\. School students \(or married to one\)\. There are no exceptions\!\n\n' \
              f'3\. List creator will be liable for the match, which means he must ensure all players have a ' \
              f'"Green Pass" and a student card in effect \(every player is responsible for bringing his\)\.\n' \
              f'In addition, he\'ll be ASAT\'s point of contact regarding any possible match\-related inquiries\.\n\n' \
              f'4\. If the list creator wishes to remove himself from the list, he must ensure that another player ' \
              f'assumes match liability\. Failing to do so will force an admin to clear the list\.\n\n' \
              f'5\. Players can only add themselves, and only once\!\n\n' \
              f'6\. If the list is already full \(max list size is 15 players\), ' \
              f'the player will be placed on a waiting list \(will be created automatically\)\.\n\n' \
              f'7\. Moving from the waiting list to the playing list is possible only if one of the players removes ' \
              f'himself from the playing list or if an admin removed one of the players\.\n\n' \
              f'8\. Every matchday, the players on the playing list MUST approve their attendance by 16:00\.\n' \
              f'Players who fail to do so will be removed from the playing list\!\n\n' \
              f'9\. Creating a list for Monday becomes possible on Saturday evening starting at 21:30\.\n\n' \
              f'10\. Telegram Bots cannot initiate a conversation with a user \(there is no way around this\)\.\n' \
              f'So, when possible, please use bot commands in a private chat @ https://t\.me/FCTechnionBot\n' \
              f'\n*Available user commands* :\n' \
              f'\n*Available only to admins* :\n' \
              f'/start \- start the bot\n'

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


def get_command_in_private_warning(user, command):
    """Return a warning message for users who privately send a command that should be sent in public"""
    return f'Hi {user.first_name},\n'\
           f'Please send the /{command} command using the group public chat!\n\n'\
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
    dp.add_handler(CommandHandler("help", help_command))

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
