import re
import logging

from telegram import TelegramError
from telegram.ext import Updater, CommandHandler

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_GROUP_INVITE_LINK, PORT

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)

logger = logging.getLogger(__name__)

# Emojis
CLIPBOARD_EMOJI_CODE = '\U0001F4CB'
OK_SIGN_EMOJI_CODE = '\U0001F44C'
SCROLL_EMOJI_CODE = '\U0001F4DC'


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
              f'/rules \- print match rules\n' \
              f'/schedule \- print the bot\'s schedule\n' \
              f'\n*Available only to admins* :\n' \
              f'/start \- start the bot\n'

    user.send_message(message, parse_mode='MarkdownV2')


def rules_command(update, context):
    """Prints the match rules"""
    user = update.message.from_user
    if str(update.message.chat.id) == TELEGRAM_CHAT_ID:
        return update.message.reply_text(get_command_in_public_warning(user, 'rules'))

    message = f'\n{SCROLL_EMOJI_CODE}{SCROLL_EMOJI_CODE}  *Match Rules*  {SCROLL_EMOJI_CODE}{SCROLL_EMOJI_CODE}\n\n' \
              f'0\. There are three \(3\) teams\. Each team consists of five \(5\) players\.\n\n' \
              f'1\. A match lasts eight \(8\) minutes or up until one team scores two \(2\) goals\.\n\n' \
              f'2\. In case of a tie, there will be two \(2\) additional minutes of stoppage time\.\n\n' \
              f'3\. In case the standard time of play passes and the game is still in play, ' \
              f'the match will have one last attack\.\n\n' \
              f'4\. The "last attack" ends when \(whichever comes first\):\n' \
              f'    a\. A team gets a goal kick\.\n' \
              f'    b\. The ball has been out for a throw\-out for the third time\.\n' \
              f'    \* corner\-kicks are considered a part of the attack\.\n\n' \
              f'5\. In case the stoppage time ends in a tie, there are two options:\n' \
              f'    a\. The veteran team \(if there is one\) leaves\.\n' \
              f'    b\. Each team gets a penalty kick\.\n' \
              f'        The first team that scores while the other misses, stays\.\n\n' \
              f'6\. The goalkeeper\'s movement is limited to his team\'s half\.\n\n' \
              f'7\. The goalkeeper can score a goal\.\n\n' \
              f'8\. The goalkeeper is replaced in each of the following cases \(whichever comes first\):\n' \
              f'    a\. He has conceded a goal\.\n' \
              f'    b\. He has been in goal the entire match \(from start to finish\)\.\n\n'

    user.send_message(message, parse_mode='MarkdownV2')


def schedule_command(update, context):
    """Prints the bot's schedule"""
    user = update.message.from_user
    if str(update.message.chat.id) == TELEGRAM_CHAT_ID:
        return update.message.reply_text(get_command_in_public_warning(user, 'schedule'))

    message = f'\n{CLIPBOARD_EMOJI_CODE}{CLIPBOARD_EMOJI_CODE}  *Bot schedule*  ' \
              f'{CLIPBOARD_EMOJI_CODE}{CLIPBOARD_EMOJI_CODE}\n\n' \
              f'0\. Each matchday at 12:30, ' \
              f'the bot will remind players who have yet to approve their attendance to do so\.\n\n' \
              f'1\. Each matchday at 15:00, ' \
              f'the bot will give a final reminder for players who have yet to approve their attendance to do so\.\n\n' \
              f'2\. Each matchday at 16:00, 16:30, 17:00, 17:30, and 18:00, ' \
              f'the bot will remove from the list players who have yet to approve their attendance\.\n' \
              f'When promoting players from the waiting list, ' \
              f'the bot will give preference to players who approved their attendance\.\n\n' \
              f'3\. Each matchday at 23:59:59, the bot will clean up the list\.\n\n' \
              f'4\. Each day at 05:00:00, the bot restarts itself\.\n' \
              f'Please refrain from performing any actions during the 10 minutes before\.\n\n'

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


def user_full_name_is_valid(user):
    """Check if user's full name is valid"""
    if len(user.first_name) <= 1 or user.last_name is None or len(user.last_name) <= 1:
        return False

    regex = re.compile('[.,@_\-!#$%^&*()<>?/\|}{~:0123456789]')
    if regex.search(user.full_name) is not None:
        return False

    return True


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
    dp.add_handler(CommandHandler("rules", rules_command))
    dp.add_handler(CommandHandler("schedule", schedule_command))

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
