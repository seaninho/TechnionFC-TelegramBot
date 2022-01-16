import re
import logging
from datetime import datetime, time
from pytz import timezone
from collections import deque

from telegram import TelegramError
from telegram.ext import Updater, CommandHandler

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_GROUP_INVITE_LINK, PORT
from TechnionFCPlayer import TechnionFCPlayer

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)

logger = logging.getLogger(__name__)

# Constants
MATCHDAYS = (0, 3)                  # matchdays are Monday and Thursday
LIST_MAX_SIZE = 15                  # there are 3 teams, each team has 5 players (set by pitch size)

# Emojis
CLIPBOARD_EMOJI_CODE = '\U0001F4CB'
OK_SIGN_EMOJI_CODE = '\U0001F44C'
SCROLL_EMOJI_CODE = '\U0001F4DC'

# Playing list. This data structure functions as a waiting list as well
playing = deque()


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
              f'9\. Creating a list for Monday becomes possible on Saturday evening starting at 21:30\.\n' \
              f'Creating a list for Thursday becomes possible on Tuesday evening starting at 21:30\.\n\n' \
              f'10\. Telegram Bots cannot initiate a conversation with a user \(there is no way around this\)\.\n' \
              f'So, when possible, please use bot commands in a private chat @ https://t\.me/FCTechnionBot\n' \
              f'\n*Available user commands* :\n' \
              f'/create \- create a new list\n' \
              f'/add \- add yourself to the list\n' \
              f'/remove \- remove yourself from the list\n' \
              f'/approve \- approve you\'ll be attending the match\n' \
              f'/rules \- print match rules\n' \
              f'/schedule \- print the bot\'s schedule\n' \
              f'\n*Available only to admins* :\n' \
              f'/start \- start the bot\n'

    user.send_message(message, parse_mode='MarkdownV2')


def create_command(update, context):
    """Create a playing list"""
    user = update.message.from_user
    if str(update.message.chat.id) == TELEGRAM_CHAT_ID:
        return update.message.reply_text(get_command_in_public_warning(user, 'create'))

    day = datetime.now(tz=timezone('Asia/Jerusalem')).weekday()
    current_time = datetime.now(tz=timezone('Asia/Jerusalem'))
    if day == 1 and current_time.time() < time(hour=21, minute=30, tzinfo=timezone('Asia/Jerusalem')):
        return user.send_message(f'Hi {user.full_name}, club rules state that creating a list for Thursday '
                                 f'becomes possible on Tuesday evening starting at 21:30!')
    if day == 4 or (day == 5 and current_time.time() < time(hour=21, minute=30, tzinfo=timezone('Asia/Jerusalem'))):
        return user.send_message(f'Hi {user.full_name}, club rules state that creating a list for Monday '
                                 f'becomes possible on Saturday evening starting at 21:30!')
    if not user_full_name_is_valid(user):
        return user.send_message(f'Hi {user.full_name}, your telegram name is invalid!\n\n'
                                 f'Please use /help to read on our naming rules, change it, and try again')

    if playing:
        return user.send_message(f'Playing list is not empty!\n\n{user.full_name}, '
                                 f'please add yourself to current queue using the /add command')

    player = TechnionFCPlayer(user, liable=True)
    playing.append(player)
    context.bot.send_message(TELEGRAM_CHAT_ID, f'{user.full_name} has created a new playing list!')
    user.send_message(f'Congratulations {user.full_name}, you\'ve created a new playing list!\n\n'
                      f'Please note, you\'re liable for the match!\n'
                      f'For more information, please see the /help message')


def add_command(update, context):
    """Add player to the playing list"""
    user = update.message.from_user
    if str(update.message.chat.id) == TELEGRAM_CHAT_ID:
        return update.message.reply_text(get_command_in_public_warning(user, 'add'))

    if not user_full_name_is_valid(user):
        return user.send_message(f'Hi {user.full_name}, your telegram name is invalid!\n\n'
                                 f'Please use /help to read on our naming rules, change it, and try again')

    player = TechnionFCPlayer(user)
    if playing.count(player) > 0:
        index = playing.index(player)
        if index < LIST_MAX_SIZE:
            return user.send_message(f'{user.full_name}, you\'re already on the playing list!')
        else:
            return user.send_message(f'{user.full_name}, you\'re already on the waiting list!')
    else:
        if len(playing) == 0:
            return user.send_message(f'{user.full_name}, please use the /create command '
                                     f'to create a list first!')

        playing.append(player)
        index = playing.index(player)
        if index < LIST_MAX_SIZE:
            return user.send_message(f'Congratulations {user.full_name}, you\'re on the playing list!\n')
        else:
            return user.send_message(f'Playing list is full!\n\n{user.full_name}, you\'re on the waiting list')


def remove_command(update, context):
    """Remove player from the playing list"""
    user = update.message.from_user
    if str(update.message.chat.id) == TELEGRAM_CHAT_ID:
        return update.message.reply_text(get_command_in_public_warning(user, 'remove'))

    player = TechnionFCPlayer(user)
    if player not in playing:
        return user.send_message(f'{user.full_name}, you\'re not listed at all!')

    index = playing.index(player)
    if playing[index].liable:
        return user.send_message(f'Hi {user.full_name}, you are liable for the match. Therefore, you cannot remove '
                                 f'yourself from the list until you ensure another player assumes match liability!')

    user.send_message(f'{user.full_name}, the bot has removed you from the playing list!')
    remove_player_from_list(context, index, player)


def approve_command(update, context):
    """Mark player approval for attending the match"""
    user = update.message.from_user
    if str(update.message.chat.id) == TELEGRAM_CHAT_ID:
        return update.message.reply_text(get_command_in_public_warning(user, 'approve'))

    day = datetime.now(tz=timezone('Asia/Jerusalem')).weekday()
    if day not in MATCHDAYS:
        return user.send_message(f'Hi {user.full_name}, please wait for matchday to approve your attendance!')

    player = TechnionFCPlayer(user)
    if player not in playing:
        return user.send_message(f'Hi {user.full_name}, you\'re not listed at all.\n\nNo need to approve!')

    index = playing.index(player)
    playing[index].approved = True
    user.send_message(f'{user.full_name}, you\'ve approved you\'ll be attending the match!')


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


def remove_player_from_list(context, index, player):
    """Remove a player from a given index on the list"""
    day = datetime.now(tz=timezone('Asia/Jerusalem')).weekday()
    current_time = datetime.now(tz=timezone('Asia/Jerusalem'))
    if day in MATCHDAYS and current_time.hour >= 17:
        # prioritizing players on the waiting list who've already approved their attendance
        first_in_line = next((player_waiting for player_waiting in playing
                              if playing.index(player_waiting) >= LIST_MAX_SIZE and player_waiting.approved),
                             playing[LIST_MAX_SIZE] if len(playing) > LIST_MAX_SIZE else None)
    else:
        first_in_line = playing[LIST_MAX_SIZE] if len(playing) > LIST_MAX_SIZE else None

    playing.remove(player)
    if index < LIST_MAX_SIZE and first_in_line is not None:
        playing.remove(first_in_line)
        playing.insert(LIST_MAX_SIZE - 1, first_in_line)  # first in line becomes last on the list
        context.bot.send_message(first_in_line.user.id, f'Congratulations {first_in_line.user.full_name}, '
                                                        f'you\'re on the playing list!')


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
    dp.add_handler(CommandHandler("create", create_command))
    dp.add_handler(CommandHandler("add", add_command))
    dp.add_handler(CommandHandler("remove", remove_command))
    dp.add_handler(CommandHandler("approve", approve_command))
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
