import re
import logging
import random
from datetime import datetime, time
from pytz import timezone
from collections import deque

from telegram import User, TelegramError
from telegram.ext import Updater, CommandHandler

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, PORT
from postgres import conn
from TechnionFCPlayer import TechnionFCPlayer

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)

logger = logging.getLogger(__name__)

# Constants
MATCHDAYS = (0, 3)                  # matchdays are Monday and Thursday
LIST_MAX_SIZE = 15                  # there are 3 teams, each team has 5 players (set by pitch size)
BACKUP_INTERVAL = 600               # backup interval set to 10 minutes
BIB_CHECK_UP_INTERVAL = 300         # check-up interval set to 5 minutes
ACCEPT_TIMEFRAME = 86400            # accept timeframe is set to 24 hours
FAKE_USER_ID = -1

# Emojis
ALARM_EMOJI_CODE = '\U000023F0'
BIB_EMOJI_CODE = '\U0001F3BD'
CALENDAR_EMOJI_CODE = '\U0001F4C5'
CHECK_MARK_EMOJI_CODE = '\U00002705'
CIRCLE_BLUE_EMOJI_CODE = '\U0001F535'
CIRCLE_GREEN_EMOJI_CODE = '\U0001F7E2'
CIRCLE_RED_EMOJI_CODE = '\U0001F534'
CLIPBOARD_EMOJI_CODE = '\U0001F4CB'
CLOCK_EMOJI_CODE = '\U0001F55A'
HOURGLASS_EMOJI_CODE = '\U000023F3'
FOOTBALL_EMOJI_CODE = '\U000026BD'
NO_ENTRY_EMOJI_CODE = '\U000026D4'
OK_SIGN_EMOJI_CODE = '\U0001F44C'
POINTING_EMOJI_CODE = '\U0000261D'
POINTING_DOWN_EMOJI_CODE = '\U0001F447'
SCROLL_EMOJI_CODE = '\U0001F4DC'
STOPWATCH_EMOJI_CODE = '\U000023F1'

# Playing list. This data structure functions as a waiting list as well
playing = deque()

# Users to be added by admins
invited = deque()

# Possible users to assume match liability
asked = deque()

# region ADMIN COMMANDS


def start_command(update, context):
    """Send bot welcome message and add jobs to the context's JobQueue"""
    user = update.message.from_user
    message = 'TechnionFC Bot has started operating\.\.\.\n\nPlease use the /help command to list your options'

    user.send_message(message, parse_mode='MarkdownV2')


def addUser_command(update, context):
    """Add player to the playing list by tagging him

    When provided with an index, the function places the tagged user in a specific place on the list"""
    user = update.message.from_user
    if str(update.message.chat.id) != TELEGRAM_CHAT_ID:
        return update.message.reply_text(f'Hi {user.full_name}, the /addUser command must be used in a public chat!')
    if not is_admin(user, update):
        return update.message.reply_text(f'Hi {user.full_name}, you\'re not an admin, '
                                         f'and therefore cannot use the /addUser command!\n'
                                         f'Please use the /add command if you wish to be added to the list.')

    # message MUST have exactly two entities to be valid: BOT_COMMAND and TEXT_MENTION or a MENTION
    if len(update.message.entities) != 2:
        return update.message.reply_text(f'Hi {user.full_name}, please make sure to tag the user you wish to add!')

    tagged_user = update.message.entities[1].user   # second message entity is a TEXT_MENTION or a MENTION

    # in case admin wants to add a player in a specific place on the list, two arguments are provided.
    index = None
    if len(context.args) == 2:
        index_str = context.args[1]                 # second argument agreed to be said place on the list
        try:
            index = int(index_str) - 1              # decreased index to accommodate "natural" indexing
        except ValueError:
            return update.message.reply_text(f'Hi {user.full_name}, please make sure to tag the user you wish '
                                             f'to add first, and the list index second!')

    if tagged_user is None:  # if second message entity is a MENTION
        return addUser_by_username(user, index, update, context)

    if not user_full_name_is_valid(tagged_user):
        return update.message.reply_text(f'Hi {user.full_name}, you\'ve tried adding a user with an invalid '
                                         f'telegram name!\n\nPlease advise him to change it and try again...')

    tagged_player = TechnionFCPlayer(tagged_user, training_bib=True)
    if tagged_player in playing:
        return update.message.reply_text(f'Hi {user.full_name}, '
                                         f'user {tagged_user.full_name} is already on the playing list!')

    if index is not None:
        playing.insert(index, tagged_player)
    else:
        playing.append(tagged_player)
    update.message.reply_text(f'Congratulations {tagged_user.full_name}, '
                              f'you were added to the playing list by {user.full_name}!')


def removeUser_command(update, context):
    """Remove tagged player from the playing list"""
    user = update.message.from_user
    if str(update.message.chat.id) != TELEGRAM_CHAT_ID:
        return update.message.reply_text(f'Hi {user.full_name}, the /removeUser command must be used in a public chat!')
    if not is_admin(user, update):
        return update.message.reply_text(f'Hi {user.full_name}, you\'re not an admin, '
                                         f'and therefore cannot use the /removeUser command!\n'
                                         f'Please use the /remove command if you wish to be removed from the list.')

    # message MUST have exactly two entities to be valid: BOT_COMMAND and TEXT_MENTION or a MENTION
    if len(update.message.entities) != 2:
        return update.message.reply_text(f'Hi {user.full_name}, please make sure to tag the user you wish to remove!')

    player, player_name = get_player_from_entity_id(update, context, entity_id=1)

    if player not in playing:
        return update.message.reply_text(f'Hi {user.full_name}, the player you wish to remove, '
                                         f'{player_name}, is not listed...\n\n'
                                         f'Please make sure to tag the correct user you wish to remove!')
    index = playing.index(player)
    if playing[index].liable:
        return update.message.reply_text(f'Hi {user.full_name}, {player_name} is liable for the match. Therefore, '
                                         f'you cannot remove him from the list until he ensures another player assumes '
                                         f'match liability!')

    # if the player hasn't accepted yet, he needs to be removed from invited too
    if player_name in invited:
        invited.remove(player_name)

    update.message.reply_text(f'{player_name} was removed from the playing list by {user.full_name}!')
    remove_player_from_list(context, index, player)


def createList_command(update, context):
    """Build list with tagged users"""
    user = update.message.from_user
    if str(update.message.chat.id) != TELEGRAM_CHAT_ID:
        return update.message.reply_text(f'Hi {user.full_name}, the /createList command must be used in a public chat!')
    if not is_admin(user, update):
        return update.message.reply_text(f'Hi {user.full_name}, you\'re not an admin, '
                                         f'and therefore cannot use the /createList command!')

    if len(context.args) != len(set(context.args)):         # not all entities are unique
        return update.message.reply_text(f'Hi {user.full_name}, please make sure not to tag the same user twice!')

    invalids = []
    for entity in update.message.entities:                  # MENTION or TEXT_MENTION are types of MessageEntity
        if entity.type not in ('mention', 'text_mention'):
            continue

        tagged_user = entity.user
        if tagged_user is None:
            continue
        if not user_full_name_is_valid(tagged_user):
            invalids.append(tagged_user)

    if invalids:
        text = f'Hi {user.full_name}, the following users have invalid telegram name:\n\n'
        for invalid in invalids:
            text += f'{invalid.full_name}\n'
        text += f'\nPlease advise them to change it and then try again!'
        return update.message.reply_text(text)

    playing.clear()                                         # clearing both queues prior to population
    invited.clear()
    for entity in update.message.entities[1:]:              # first MessageEntity is of type 'bot_command'
        tagged_user = entity.user
        if tagged_user is None:
            index = update.message.entities.index(entity)
            tagged_username = context.args[index - 1]       # argument index = entity index - 1
            username = tagged_username.replace('@', '')
            fake_user = User(FAKE_USER_ID, 'Reserved for', is_bot=False, last_name=username, username=username)
            fake_player = TechnionFCPlayer(fake_user, training_bib=True)
            invited.append(username)
            playing.append(fake_player)

            text = f'Hi @{username},\n{user.full_name} is trying to add you to the playing list\n\n' \
                   f'Your spot is reserved for the next 24 hours.\n' \
                   f'Please respond to this message with /accept'

            context.job_queue.run_once(check_accepted, ACCEPT_TIMEFRAME, context=(update.message.chat_id, username))
            update.message.reply_text(text)
        else:
            tagged_player = TechnionFCPlayer(tagged_user, training_bib=True)
            playing.append(tagged_player)
            text = f'Congratulations {tagged_user.full_name}, you were added to the playing list by {user.full_name}!'
            update.message.reply_text(text)


def clearAll_command(update, context):
    """Clear both playing and waiting lists"""
    user = update.message.from_user
    if str(update.message.chat.id) != TELEGRAM_CHAT_ID:
        return update.message.reply_text(f'Hi {user.full_name}, '
                                         f'the /clearAll command is to be used only in a public chat!')
    if is_admin(user, update):
        playing.clear()
        invited.clear()
        asked.clear()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM PLAYING")  # delete current tables
            cur.execute("DELETE FROM INVITED")
            cur.execute("DELETE FROM ASKED")
        conn.commit()
        return update.message.reply_text('Both lists were cleared by an admin')
    update.message.reply_text(f'Hi {user.full_name}!\n\nPlease note, only admins are allowed to clear the lists!')


def transferLiability_command(update, context):
    """Transfer match liability from one player to another"""
    user = update.message.from_user
    if str(update.message.chat.id) != TELEGRAM_CHAT_ID:
        return update.message.reply_text(f'Hi {user.full_name}, '
                                         f'the /transferLiability command must be used only in a public chat!')
    if not is_admin(user, update):
        return update.message.reply_text(f'Hi {user.full_name}, you\'re not an admin, '
                                         f'and therefore cannot use the /transferLiability command!')

    # message MUST have exactly three entities to be valid: BOT_COMMAND and two TEXT_MENTION or MENTION
    if len(update.message.entities) != 3:
        return update.message.reply_text(f'Hi {user.full_name}, please make sure to tag both users!')

    liable_player, liable_player_name = get_player_from_entity_id(update, context, entity_id=1)
    assuming_player, assuming_player_name = get_player_from_entity_id(update, context, entity_id=2)

    for player, player_name in (liable_player, liable_player_name), (assuming_player, assuming_player_name):
        if player not in playing:
            return update.message.reply_text(f'Hi {user.full_name}, {player_name} is not listed...\n\n'
                                             f'Please make sure to tag the correct users!')
    index_liable = playing.index(liable_player)
    if not playing[index_liable].liable:
        return update.message.reply_text(f'Hi {user.full_name}, {liable_player_name} is not liable for the match. '
                                         f'Please make sure to tag the correct users!')

    index_assuming = playing.index(assuming_player)
    playing[index_liable].liable = False
    playing[index_assuming].liable = True
    text = f'{user.full_name} has transferred match liability from {liable_player_name} to {assuming_player_name}!'
    update.message.reply_text(text)


def liableUser_command(update, context):
    """Grant match liability to a specific player"""
    user = update.message.from_user
    if str(update.message.chat.id) != TELEGRAM_CHAT_ID:
        return update.message.reply_text(f'Hi {user.full_name}, '
                                         f'the /liableUser command must be used only in a public chat!')
    if not is_admin(user, update):
        return update.message.reply_text(f'Hi {user.full_name}, you\'re not an admin, '
                                         f'and therefore cannot use the /liableUser command!')

    # message MUST have exactly two entities to be valid: BOT_COMMAND and TEXT_MENTION or a MENTION
    if len(update.message.entities) != 2:
        return update.message.reply_text(f'Hi {user.full_name}, '
                                         f'please make sure to tag the user you wish to grant match liability to!')

    liable_player, liable_player_name = get_player_from_entity_id(update, context, entity_id=1)

    if liable_player not in playing:
        return update.message.reply_text(f'Hi {user.full_name}, {liable_player_name} is not listed...\n\n'
                                         f'Please make sure to tag the correct user!')

    for player in playing:
        if player.liable:
            return update.message.reply_text(f'Hi {user.full_name}, '
                                             f'{player.user.full_name} is already liable for the match...\n\n'
                                             f'Please use the /transferLiability command to transfer match liability!')

    index_liable = playing.index(liable_player)
    playing[index_liable].liable = True
    update.message.reply_text(f'{liable_player_name} is now liable for the match!')

# endregion

# region USER COMMANDS


def help_command(update, context):
    """Send bot help message"""
    user = update.message.from_user
    if str(update.message.chat.id) == TELEGRAM_CHAT_ID:
        return update.message.reply_text(get_command_in_public_warning(user, 'help'))

    message = f'Welcome to the *Technion Football Club*\!\n\n'\
              f'This bot\'s purpose is to ease the players\' registration process {OK_SIGN_EMOJI_CODE}\n' \
              f'\n*Club rules* :\n' \
              f'0\. Club matchdays are: _Monday @ 20:00\-22:30, Thursday @ 20:00\-22:00_\n' \
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
              f'9\. Training bibs are MANDATORY\!\nPlayers who do not have one, must purchase one to play\.\n' \
              f'The link for purchasing the agreed\-upon bib can be found here https://t\.me/c/1760505503/5543\n' \
              f'Players who do not approve of wearing bibs will be removed from the playing list\!\n\n' \
              f'10\. Creating a list for Monday becomes possible on Saturday evening starting at 21:30\.\n' \
              f'Creating a list for Thursday becomes possible on Tuesday evening starting at 21:30\.\n\n' \
              f'11\. Telegram Bots cannot initiate a conversation with a user \(there is no way around this\)\.\n' \
              f'So, when possible, please use bot commands in a private chat @ https://t\.me/FCTechnionBot\n' \
              f'\n*Available user commands* :\n' \
              f'/create \- create a new list\n' \
              f'/add \- add yourself to the list\n' \
              f'/remove \- remove yourself from the list\n' \
              f'/liable \- ask the tagged user to assume match liability\n' \
              f'/accept \- accept admin invitation to join the list\n' \
              f'/approve \- approve you\'ll be attending the match\n' \
              f'/assume \- assume match liability\n' \
              f'/bib \- approve you\'ll be bringing the training bib\n' \
              f'/ball \- inform you\'ll be bringing a match ball\n' \
              f'/print \- print the list\n' \
              f'/shuffle \- shuffle the playing list to create 3 random teams\n' \
              f'/rules \- print match rules\n' \
              f'/schedule \- print the bot\'s schedule\n' \
              f'\n*Available only to admins* :\n' \
              f'/start \- start the bot\n' \
              f'/addUser \- add the tagged user to the list\n' \
              f'/removeUser \- remove the tagged user from the list\n' \
              f'/createList \- create a new list with tagged users\n' \
              f'/clearAll \- clear the list\n' \
              f'/transferLiability \- transfer match liability between tagged users\n' \
              f'/liableUser \- grant match liability to the tagged user\n'

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
                      f'For more information, please see the /help message.\n\n'
                      f'Please use the /bib command to approve you\'ll be bringing the training bib!')
    context.job_queue.run_once(check_training_bib, BIB_CHECK_UP_INTERVAL, context=user)


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
            user.send_message(f'Congratulations {user.full_name}, you\'re on the playing list!\n'
                              f'Please use the /bib command to approve you\'ll be bringing the training bib!')
        else:
            user.send_message(f'Playing list is full!\n\n{user.full_name}, you\'re on the waiting list...\n'
                              f'Please use the /bib command to approve you\'ll be bringing the training bib!')

        context.job_queue.run_once(check_training_bib, BIB_CHECK_UP_INTERVAL, context=user)


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


def liable_command(update, context):
    """Ask the tagged user to assume match liability"""
    user = update.message.from_user

    if str(update.message.chat.id) != TELEGRAM_CHAT_ID:
        return user.send_message(f'Hi {user.full_name}, the /liable command cannot be used in a private chat!')

    player = TechnionFCPlayer(user)
    if player not in playing:
        return user.send_message(f'Hi {user.full_name}, you\'re not listed at all and therefore not liable!')

    index = playing.index(player)
    if not playing[index].liable:
        return user.send_message(f'Hi {user.full_name}, you\'re not liable and therefore cannot transfer liability!')

    # message MUST have exactly two entities to be valid: BOT_COMMAND and TEXT_MENTION or a MENTION
    if len(update.message.entities) != 2:
        return user.send_message(f'Hi {user.full_name}, please tag the user you wish will assume match liability!')

    player, player_name = get_player_from_entity_id(update, context, entity_id=1)

    if player not in playing:
        return user.send_message(f'Hi {user.full_name}, the user you tagged, {player_name}, is not listed...\n\n'
                                 f'Please tag the correct user you wish will assume match liability!')
    index = playing.index(player)
    if playing[index].user.id == FAKE_USER_ID:
        return user.send_message(f'Hi {user.full_name}, the user you tagged, {player_name}, '
                                 f'has yet to accept the admin\'s invitation to join the list...\n\n'
                                 f'Please tag a user on the playing list!')

    if index >= LIST_MAX_SIZE:
        return user.send_message(f'Hi {user.full_name}, the user you tagged, {player_name}, '
                                 f'is on the waiting list...\n\n'
                                 f'Please tag the correct user you wish will assume match liability!')

    user_id_or_name = str(playing[index].user.id) \
        if not playing[index].user.username \
        else playing[index].user.username
    if user_id_or_name in asked:
        return user.send_message(f'Hi {user.full_name}, the user you tagged, {player_name}, '
                                 f'has already been asked to assume match liability!')

    asked.append(user_id_or_name)
    update.message.reply_text(f'Hi {player_name}, {user.full_name} has asked you to assume match liability.\n\n'
                              f'Please use the /assume command to assume match liability!')


def accept_command(update, context):
    """Accept admin invitation to join the list"""
    user = update.message.from_user
    if user.username not in invited:
        return user.send_message(f'Hi {user.full_name},\nYou were not invited by an admin!')

    if not user_full_name_is_valid(user):
        return user.send_message(f'Hi {user.full_name}, your telegram name is invalid!\n\n'
                                 f'Please use /help to read on our naming rules, change it, and try again')

    # for each invited player, there is a single fake player on the playing list with the same (unique) username
    fake_player = [player for player in playing if player.user.username == user.username].pop()

    index = playing.index(fake_player)
    playing.remove(fake_player)
    playing.insert(index, TechnionFCPlayer(user))
    invited.remove(user.username)
    if index < LIST_MAX_SIZE:
        return user.send_message(f'Congratulations {user.full_name}, you\'re on the playing list!\n')
    user.send_message(f'Hi {user.full_name}, you\'re on the waiting list')


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


def assume_command(update, context):
    """Assume match liability"""
    user = update.message.from_user
    player = TechnionFCPlayer(user)
    if player not in playing:
        return user.send_message(f'Hi {user.full_name}, you\'re not listed at all.\n\n'
                                 f'No need to assume match liability!')

    index = playing.index(player)
    if playing[index].liable:
        return user.send_message(f'Hi {user.full_name}, you\'re already liable!\n\nNo need to assume match liability!')

    if playing[index].user.id == FAKE_USER_ID:
        return user.send_message(f'Hi {user.full_name}, '
                                 f'please /accept admin invitation before assuming match liability!')

    user_id_or_name = str(user.id) if user.username is None else user.username
    if user_id_or_name not in asked:
        return user.send_message(f'Hi {user.full_name},\nYou were not asked to assume match liability!')

    for player in playing:
        player.liable = False
    playing[index].liable = True

    asked.clear()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ASKED")
    context.bot.send_message(TELEGRAM_CHAT_ID, f'{user.full_name} has assumed match liability!')


def bib_command(update, context):
    """Mark player approval for bringing the training bib"""
    user = update.message.from_user
    if str(update.message.chat.id) == TELEGRAM_CHAT_ID:
        return update.message.reply_text(get_command_in_public_warning(user, 'bib'))

    player = TechnionFCPlayer(user)
    if player not in playing:
        return user.send_message(f'Hi {user.full_name}, you\'re not listed at all.\n\n'
                                 f'No need to bring the training bib!')

    index = playing.index(player)
    playing[index].training_bib = not playing[index].training_bib
    if playing[index].training_bib:
        user.send_message(f'Hi {user.full_name}, you\'ve approved you\'ll be bringing the training bib!')
    else:
        user.send_message(f'Hi {user.full_name},\n'
                          f'Please use the /bib command to approve you\'ll be bringing the training bib!')
        context.job_queue.run_once(check_training_bib, BIB_CHECK_UP_INTERVAL, context=player)


def ball_command(update, context):
    """Mark player approval for bringing a match ball"""
    user = update.message.from_user
    if str(update.message.chat.id) == TELEGRAM_CHAT_ID:
        return update.message.reply_text(get_command_in_public_warning(user, 'ball'))

    player = TechnionFCPlayer(user)
    if player not in playing:
        return user.send_message(f'Hi {user.full_name}, you\'re not listed at all.\n\nNo need to bring a match ball!')
    index = playing.index(player)
    playing[index].match_ball = not playing[index].match_ball
    if playing[index].match_ball:
        user.send_message(f'Hi {user.full_name}, you\'re in charge of bringing a match ball!')
    else:
        user.send_message(f'Hi {user.full_name}, you\'re not in charge of bringing a match ball anymore')


def print_command(update, context):
    """Print both playing and waiting lists"""
    user = update.message.from_user
    if str(update.message.chat.id) == TELEGRAM_CHAT_ID:
        return update.message.reply_text(get_command_in_public_warning(user, 'print'))

    user.send_message(get_lists(), parse_mode='MarkdownV2')


def shuffle_command(update, context):
    """Shuffle playing list to create 3 unique teams"""
    user = update.message.from_user
    if str(update.message.chat.id) == TELEGRAM_CHAT_ID:
        return update.message.reply_text(get_command_in_public_warning(user, 'shuffle'))

    day = datetime.now(tz=timezone('Asia/Jerusalem')).weekday()
    current_time = datetime.now(tz=timezone('Asia/Jerusalem'))
    # shuffle is allowed only on matchdays and only past 19:30
    if day not in MATCHDAYS or current_time.time() < time(hour=19, minute=30, tzinfo=timezone('Asia/Jerusalem')):
        return user.send_message(f'Hi {user.full_name}, '
                                 f'shuffle command is reserved for matchdays, starting from 19:30!')

    min_for_shuffle = 12
    if len(playing) < min_for_shuffle:
        return user.send_message(f'Hi {user.full_name}, there aren\'t enough players for a match shuffle...')

    teams = {}
    colors = ('Red', 'Green', 'Blue')
    players = [player for player in playing if playing.index(player) < LIST_MAX_SIZE]
    random.shuffle(players)

    text = 'One possible way to divide into 3 teams\n\n'
    for color in colors:
        teams[color] = players[colors.index(color)::3]
        if color == 'Red':
            text += f'{CIRCLE_RED_EMOJI_CODE}{CIRCLE_RED_EMOJI_CODE}  {color} Team  ' \
                   f'{CIRCLE_RED_EMOJI_CODE}{CIRCLE_RED_EMOJI_CODE}\n\n'
        elif color == 'Green':
            text += f'{CIRCLE_GREEN_EMOJI_CODE}{CIRCLE_GREEN_EMOJI_CODE}  {color} Team  ' \
                   f'{CIRCLE_GREEN_EMOJI_CODE}{CIRCLE_GREEN_EMOJI_CODE}\n\n'
        else:
            text += f'{CIRCLE_BLUE_EMOJI_CODE}{CIRCLE_BLUE_EMOJI_CODE}  {color} Team  ' \
                   f'{CIRCLE_BLUE_EMOJI_CODE}{CIRCLE_BLUE_EMOJI_CODE}\n\n'
        team_players = teams[color]
        for player in team_players:
            text += f'{team_players.index(player) + 1}\. {player.user.first_name} {player.user.last_name}\n'
        text += '\n'
    user.send_message(text, parse_mode='MarkdownV2')


def rules_command(update, context):
    """Prints the match rules"""
    user = update.message.from_user
    if str(update.message.chat.id) == TELEGRAM_CHAT_ID:
        return update.message.reply_text(get_command_in_public_warning(user, 'rules'))

    message = f'\n{SCROLL_EMOJI_CODE}{SCROLL_EMOJI_CODE}  *Match Rules*  {SCROLL_EMOJI_CODE}{SCROLL_EMOJI_CODE}\n\n' \
              f'0\. There are three \(3\) teams\. Each team consists of five \(5\) players\.\n\n' \
              f'1\. Each player must have a blue and green training bib\.\n\n' \
              f'2\. A match lasts eight \(8\) minutes or up until one team scores two \(2\) goals\.\n\n' \
              f'3\. In case of a tie, there will be two \(2\) additional minutes of stoppage time\.\n\n' \
              f'4\. In case the standard time of play passes and the game is still in play, ' \
              f'the match will have one last attack\.\n\n' \
              f'5\. The "last attack" ends when \(whichever comes first\):\n' \
              f'    a\. A team gets a goal kick\.\n' \
              f'    b\. The ball has been out for a throw\-out for the third time\.\n' \
              f'    \* corner\-kicks are considered a part of the attack\.\n\n' \
              f'6\. In case the stoppage time ends in a tie, there are two options:\n' \
              f'    a\. The veteran team \(if there is one\) leaves\.\n' \
              f'    b\. Each team gets a penalty kick\.\n' \
              f'        The first team that scores while the other misses, stays\.\n\n' \
              f'7\. The goalkeeper\'s movement is limited to his team\'s half\.\n\n' \
              f'8\. The goalkeeper can score a goal\.\n\n' \
              f'9\. The goalkeeper is replaced in each of the following cases \(whichever comes first\):\n' \
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
              f'0\. Once a player has added himself to the playing list, ' \
              f'he has 5 minutes to approve he will be bringing the training bib\.\n' \
              f'Failing to do so on time will cause the bot to remove said player from the playing list\.\n\n' \
              f'1\. Each matchday at 12:30, ' \
              f'the bot will remind players who have yet to approve their attendance to do so\.\n\n' \
              f'2\. Each matchday at 15:00, ' \
              f'the bot will give a final reminder for players who have yet to approve their attendance to do so\.\n\n' \
              f'3\. Each matchday at 16:00, 16:30, 17:00, 17:30, and 18:00, ' \
              f'the bot will remove from the list players who have yet to approve their attendance\.\n' \
              f'When promoting players from the waiting list, ' \
              f'the bot will give preference to players who approved their attendance\.\n\n' \
              f'4\. Each matchday at 11:15, 13:15, 15:15, 17:15, 18:15, and 19:15, the bot will print ' \
              f'the current state of the list\.\n\n' \
              f'5\. Each matchday at 23:59:59, the bot will clean up the list\.\n\n' \
              f'6\. Each day at 05:00:00, the bot restarts itself\.\n' \
              f'Please refrain from performing any actions during the 10 minutes before\.\n\n'

    user.send_message(message, parse_mode='MarkdownV2')


def isGroupMember_command(update, context):
    """Check if user is a group member"""
    user = update.message.from_user
    try:
        chat_member = context.bot.get_chat_member(TELEGRAM_CHAT_ID, user.id)
    except TelegramError:
        return update.message.reply_text(f'Hi {user.full_name}, you are not a part of the Technion FC group...')
    return update.message.reply_text(f'Hi {user.full_name}, you are a part of the Technion FC group!')

# endregion

# region TELEGRAM JOBS


def backup_to_database(context):
    """Backup list to database"""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM PLAYING")          # delete current table
        for player in playing:
            user_id = player.user.id
            user_first_name = player.user.first_name
            user_last_name = player.user.last_name
            user_username = player.user.username if player.user.username is not None else ''
            player_liable = player.liable
            player_approved = player.approved
            player_match_ball = player.match_ball
            player_training_bib = player.training_bib
            cur.execute("INSERT INTO PLAYING (user_id, user_first_name, user_last_name, user_username, "
                        "player_liable, player_approved, player_match_ball, player_training_bib)"
                        "VALUES(%s, %s, %s, %s, %s, %s, %s, %s)",
                        (user_id, user_first_name, user_last_name, user_username,
                         player_liable, player_approved, player_match_ball, player_training_bib))
            conn.commit()

        cur.execute("DELETE FROM INVITED")
        for username in invited:
            # cur.execute inserted value must be a tuple
            cur.execute("INSERT INTO INVITED (username) VALUES(%s)", (username,))
            conn.commit()

        cur.execute("DELETE FROM ASKED")
        for user_id_or_name in asked:
            # cur.execute inserted value must be a tuple
            cur.execute("INSERT INTO ASKED (user_id_or_name) VALUES(%s)", (user_id_or_name,))
            conn.commit()


def kindly_reminder(context):
    """Remind players to approve their attendance"""
    if all(player.approved for player in playing):
        return

    text = f'{ALARM_EMOJI_CODE}  It\'s 12:30 on matchday  {ALARM_EMOJI_CODE}\n\n' \
           f'This is a kindly reminder for\n\n'
    yet_to_approve = [player for player in playing if not player.approved]
    for player in yet_to_approve:
        if player.user.id == FAKE_USER_ID:
            text += f'\@{player.user.username}\n'
        else:
            text += f'{player.user.mention_markdown_v2()}\n'
    text += '\nPlease approve you\'ll be attending the match\!'

    context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode='MarkdownV2')


def final_reminder(context):
    """Final reminder for players to approve their attendance"""
    if all(player.approved for player in playing):
        return

    text = ''
    playing_yet_to_approve = [player for player in playing
                              if playing.index(player) < LIST_MAX_SIZE and not player.approved]
    if playing_yet_to_approve:
        text += f'{ALARM_EMOJI_CODE}  It\'s 15:00 on matchday  {ALARM_EMOJI_CODE}\n\n' \
               f'This is a final reminder for\n\n'
        for player in playing_yet_to_approve:
            if player.user.id == FAKE_USER_ID:
                text += f'\@{player.user.username}\n'
            else:
                text += f'{player.user.mention_markdown_v2()}\n'
        text += f'\nPlease approve you\'ll be attending the match\!\n' \
                f'{NO_ENTRY_EMOJI_CODE}  *If you will not approve your attendance in the next hour, ' \
                f'you\'ll lose your place on the playing list\!*  {NO_ENTRY_EMOJI_CODE}'

    if len(playing) > LIST_MAX_SIZE:        # waiting list is not empty
        waiting_yet_to_approve = [player for player in playing
                                  if playing.index(player) >= LIST_MAX_SIZE and not player.approved]
        if waiting_yet_to_approve:
            if playing_yet_to_approve:
                text += f'\n\nThis is also a kindly reminder for\n\n'
            else:
                text += f'{ALARM_EMOJI_CODE}  It\'s 16:00 on matchday  {ALARM_EMOJI_CODE}\n\n' \
                        f'This is a kindly reminder for\n\n'
            for player in waiting_yet_to_approve:
                if player.user.id == FAKE_USER_ID:
                    text += f'\@{player.user.username}\n'
                else:
                    text += f'{player.user.mention_markdown_v2()}\n'
            text += f'\n*It is advisable to approve your attendance\!*\nWhen promoting players from ' \
                    f'the waiting list, the bot will prioritize players who\'ve approved their attendance\!'

    if text:
        context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode='MarkdownV2')


def remove_non_attenders(context):
    """Remove players on the playing list who didn't approve their attendance in time

    Such players will be replaced with players on the waiting list (preferably, ones who've approved) if there are any.
    Move the non-attenders to the back of the waiting list"""
    if all(player.approved for player in playing):
        return

    yet_to_approve = [player for player in playing if playing.index(player) < LIST_MAX_SIZE and not player.approved]
    for player in yet_to_approve:
        if player.liable:
            continue
        if player.user.id == FAKE_USER_ID:
            text = f'\@{player.user.username}, '
        else:
            text = f'{player.user.mention_markdown_v2()}, '
        text += f'the bot removed you from the playing list for failing to approve your attendance in time\.\n\n'

        # prioritizing players on the waiting list who've already approved their attendance
        first_in_line = next((player_waiting for player_waiting in playing
                              if playing.index(player_waiting) >= LIST_MAX_SIZE and player_waiting.approved),
                             playing[LIST_MAX_SIZE] if len(playing) > LIST_MAX_SIZE else None)

        playing.remove(player)
        if first_in_line is not None:       # waiting list is not empty
            if first_in_line.user.id == FAKE_USER_ID:
                text += f'Congratulations \@{first_in_line.user.username}, you\'ve made the playing list\!'
            else:
                text += f'Congratulations {first_in_line.user.mention_markdown_v2()}, you\'ve made the playing list\!'
            if not first_in_line.approved:
                text += f'\nPlease approve you\'ll be attending the match\!'
            playing.remove(first_in_line)
            playing.insert(LIST_MAX_SIZE - 1, first_in_line)

        context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode='MarkdownV2')


def check_training_bib(context):
    """Check if the user approved on time that he'll be bringing the training bib"""
    user = context.job.context
    player = TechnionFCPlayer(user)
    if player not in playing:
        return

    index = playing.index(player)
    player = playing[index]
    if player.training_bib:
        return

    if player.liable:
        text = f'Hi {player.user.mention_markdown_v2()},\n' \
               f'The timeframe for approving you\'ll be bringing the training bib has passed\!\n\n' \
               f'Please transfer match liability if you do not have a bib or use the bib command to approve you will' \
               f'be bringing the training bib\.'
        return context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode='MarkdownV2')

    index = playing.index(player)
    remove_player_from_list(context, index, player)
    text = f'Hi {player.user.full_name}, the bot has removed you from the playing list for failing to approve ' \
           f'you\'ll be brining the training bib in time.\n\n'
    context.bot.send_message(chat_id=player.user.id, text=text)


def print_lists(context):
    """Print both playing and waiting lists"""
    if not playing:     # playing list is empty. Therefore, no need to print it.
        return
    text = f'{POINTING_DOWN_EMOJI_CODE}  Current state of the list  {POINTING_DOWN_EMOJI_CODE}\n\n'
    text += get_lists()
    if context.job.context:
        text += f'\n\n{BIB_EMOJI_CODE}{BIB_EMOJI_CODE}{BIB_EMOJI_CODE}' \
                f'\nDon\'t forget to bring your training bib\!\n' \
                f'{BIB_EMOJI_CODE}{BIB_EMOJI_CODE}{BIB_EMOJI_CODE}'
    context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode='MarkdownV2')


def list_cleanup(context):
    """Clear the playing list"""
    if not playing:     # playing list is empty. Therefore, no need to clear it.
        return
    text = f'{CLOCK_EMOJI_CODE}  It\'s time for the bot\'s scheduled cleanup\.\.\.  {CLOCK_EMOJI_CODE}\n\n'
    playing.clear()
    invited.clear()
    asked.clear()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM PLAYING")          # delete current tables
        cur.execute("DELETE FROM INVITED")
        cur.execute("DELETE FROM ASKED")
    conn.commit()
    text += 'List was cleared by the bot\!'
    context.bot.send_message(chat_id=context.job.context, text=text, parse_mode='MarkdownV2')


def check_accepted(context):
    """Check if user has accepted the administrator's invitation"""
    username = context.job.context
    if username not in invited:
        return

    fake_user = User(id=FAKE_USER_ID, first_name='Reserved for', is_bot=False, last_name=username, username=username)
    fake_player = TechnionFCPlayer(fake_user)
    index = playing.index(fake_player)

    text = f'Hi @{username}, timeframe for accepting the admin\'s invitation has passed!\n' \
           f'Please contact an admin to get re-invited.'
    context.bot.send_message(TELEGRAM_CHAT_ID, text)

    invited.remove(username)
    remove_player_from_list(context, index, fake_player)

# endregion

# region HELPER FUNCTIONS


def is_admin(user, update):
    """Check if user is an admin"""
    admins = update.effective_chat.get_administrators()
    for admin in admins:
        if user == admin.user:
            return True
    return False


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
           f'Please send the /{command} command via the bot\'s private chat @ https://t.me/FCTechnionBot.\n\n'\
           f'If you have any questions, feel free to ask :)'


def get_lists():
    """Return playing and waiting lists"""
    day = datetime.now(tz=timezone('Asia/Jerusalem')).weekday()
    if 1 <= day <= 3:  # Tuesday - Thursday
        text = f'{CALENDAR_EMOJI_CODE}  *Thursday 20:00*  {CALENDAR_EMOJI_CODE}\n\n'
    else:  # Friday - Monday
        text = f'{CALENDAR_EMOJI_CODE}  *Monday 20:00*  {CALENDAR_EMOJI_CODE}\n\n'

    waiting_flag = False
    text += f'{STOPWATCH_EMOJI_CODE}{STOPWATCH_EMOJI_CODE}  Playing list  ' \
            f'{STOPWATCH_EMOJI_CODE}{STOPWATCH_EMOJI_CODE}\n\n'

    for player in playing:
        index = playing.index(player)
        if index >= LIST_MAX_SIZE and not waiting_flag:
            text += f'\n{HOURGLASS_EMOJI_CODE}{HOURGLASS_EMOJI_CODE}  Waiting list  ' \
                    f'{HOURGLASS_EMOJI_CODE}{HOURGLASS_EMOJI_CODE}\n\n'
            waiting_flag = True
        if not waiting_flag:
            text += f'{index + 1}\. {player.user.full_name}'
        else:
            text += f'{index + 1 - LIST_MAX_SIZE}\. {player.user.full_name}'
        if player.liable:
            text += f'  {POINTING_EMOJI_CODE}'
        if player.approved:
            text += f'  {CHECK_MARK_EMOJI_CODE}'
        if player.training_bib:
            text += f'  {BIB_EMOJI_CODE}'
        if player.match_ball:
            text += f'  {FOOTBALL_EMOJI_CODE}'
        text += '\n'
    return text


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
        if first_in_line.user.id != FAKE_USER_ID:
            context.bot.send_message(first_in_line.user.id, f'Congratulations {first_in_line.user.full_name}, '
                                                            f'you\'re on the playing list!')
        else:
            context.bot.send_message(TELEGRAM_CHAT_ID, f'Congratulations @{first_in_line.user.username}, '
                                                       f'you\'re onr the playing list!')


def addUser_by_username(user, index, update, context):
    """Add player to the playing list using tagged username"""
    tagged_username = context.args[0]
    username = tagged_username.replace('@', '')

    if username in invited:
        return update.message.reply_text(f'Hi {user.full_name},\n'
                                         f'Bot is currently waiting for {username} to accept your invitation!')

    fake_user = User(id=FAKE_USER_ID, first_name='Reserved for', is_bot=False, last_name=username, username=username)
    fake_player = TechnionFCPlayer(fake_user)
    text = f'Hi @{username},\n{user.full_name} is trying to add you to the playing list\n\n'

    invited.append(username)
    if index is not None:
        playing.insert(index, fake_player)
    else:
        playing.append(fake_player)

    text += f'Your spot is reserved for the next 24 hours.\n' \
            f'Please respond to this message with /accept'

    context.job_queue.run_once(check_accepted, ACCEPT_TIMEFRAME, context=username)
    return update.message.reply_text(text)


def get_player_from_entity_id(update, context, entity_id):
    """Get player (and player name) using message entity id"""
    tagged_user = update.message.entities[entity_id].user   # second message entity is a TEXT_MENTION or a MENTION
    if tagged_user is None:                                 # if message entity is a MENTION
        tagged_username = context.args[entity_id-1]
        username = tagged_username.replace('@', '')
        fake_user = User(FAKE_USER_ID, first_name='', is_bot=False, username=username)
        player = TechnionFCPlayer(fake_user)
        player_name = username
    else:                                                   # message entity is a TEXT_MENTION
        player = TechnionFCPlayer(tagged_user)
        player_name = tagged_user.full_name
    return player, player_name


def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def restore_from_database():
    """Restore playing list from database back up"""
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM PLAYING")
        players_data = cur.fetchall()
        cur.execute("SELECT * FROM INVITED")
        invited_data = cur.fetchall()
        cur.execute("SELECT * FROM ASKED")
        asked_data = cur.fetchall()

    for player_data in players_data:
        (user_id, user_first_name, user_last_name, user_username,
         player_liable, player_approved, player_match_ball, player_training_bib) = player_data
        user = User(user_id, first_name=user_first_name, is_bot=False, last_name=user_last_name, username=user_username)
        player = TechnionFCPlayer(user, player_liable, player_approved, player_match_ball, player_training_bib)
        playing.append(player)

    for invited_tuple in invited_data:
        (invited_player,) = invited_tuple
        invited.append(invited_player)

    for asked_tuple in asked_data:
        (asked_player,) = asked_tuple
        asked.append(asked_player)

# endregion


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
    dp.add_handler(CommandHandler("liable", liable_command))
    dp.add_handler(CommandHandler("accept", accept_command))
    dp.add_handler(CommandHandler("approve", approve_command))
    dp.add_handler(CommandHandler("assume", assume_command))
    dp.add_handler(CommandHandler("bib", bib_command))
    dp.add_handler(CommandHandler("ball", ball_command))
    dp.add_handler(CommandHandler("print", print_command))
    dp.add_handler(CommandHandler("shuffle", shuffle_command))
    dp.add_handler(CommandHandler("rules", rules_command))
    dp.add_handler(CommandHandler("schedule", schedule_command))
    dp.add_handler(CommandHandler("addUser", addUser_command))
    dp.add_handler(CommandHandler("removeUser", removeUser_command))
    dp.add_handler(CommandHandler("createList", createList_command))
    dp.add_handler(CommandHandler("clearAll", clearAll_command))
    dp.add_handler(CommandHandler("transferLiability", transferLiability_command))
    dp.add_handler(CommandHandler("liableUser", liableUser_command))
    dp.add_handler(CommandHandler("isGroupMember", isGroupMember_command))

    # log all errors
    dp.add_error_handler(error)

    # restore data from back up
    restore_from_database()

    # run backup_to_database every hour
    dp.job_queue.run_repeating(backup_to_database, BACKUP_INTERVAL)

    # run kindly_reminder every matchday @ 12:30
    dp.job_queue.run_daily(kindly_reminder,
                           time(hour=12, minute=30, tzinfo=timezone('Asia/Jerusalem')),
                           days=MATCHDAYS)

    # run final_reminder every matchday @ 15:00
    dp.job_queue.run_daily(final_reminder,
                           time(hour=15, minute=0, tzinfo=timezone('Asia/Jerusalem')),
                           days=MATCHDAYS)

    # run remove_non_attenders every matchday @ 16:00, 16:30, 17:00, 17:30, 18:00
    dp.job_queue.run_daily(remove_non_attenders,
                           time(hour=16, minute=0, tzinfo=timezone('Asia/Jerusalem')),
                           days=MATCHDAYS)
    dp.job_queue.run_daily(remove_non_attenders,
                           time(hour=16, minute=30, tzinfo=timezone('Asia/Jerusalem')),
                           days=MATCHDAYS)
    dp.job_queue.run_daily(remove_non_attenders,
                           time(hour=17, minute=0, tzinfo=timezone('Asia/Jerusalem')),
                           days=MATCHDAYS)
    dp.job_queue.run_daily(remove_non_attenders,
                           time(hour=17, minute=30, tzinfo=timezone('Asia/Jerusalem')),
                           days=MATCHDAYS)
    dp.job_queue.run_daily(remove_non_attenders,
                           time(hour=18, minute=0, tzinfo=timezone('Asia/Jerusalem')),
                           days=MATCHDAYS)

    # run print_list every matchday @ 11:15, 13:15, 15:15, 17:15, 18:15, and 19:15
    dp.job_queue.run_daily(print_lists,
                           time(hour=11, minute=15, tzinfo=timezone('Asia/Jerusalem')),
                           days=MATCHDAYS)
    dp.job_queue.run_daily(print_lists,
                           time(hour=13, minute=15, tzinfo=timezone('Asia/Jerusalem')),
                           days=MATCHDAYS)
    dp.job_queue.run_daily(print_lists,
                           time(hour=15, minute=15, tzinfo=timezone('Asia/Jerusalem')),
                           days=MATCHDAYS)
    dp.job_queue.run_daily(print_lists,
                           time(hour=17, minute=15, tzinfo=timezone('Asia/Jerusalem')),
                           days=MATCHDAYS)
    dp.job_queue.run_daily(print_lists,
                           time(hour=18, minute=15, tzinfo=timezone('Asia/Jerusalem')),
                           days=MATCHDAYS)
    dp.job_queue.run_daily(print_lists,
                           time(hour=19, minute=15, tzinfo=timezone('Asia/Jerusalem')),
                           days=MATCHDAYS,
                           context=True)

    # run clear_list every matchday @ 23:59:59
    dp.job_queue.run_daily(list_cleanup,
                           time(hour=23, minute=59, second=59, tzinfo=timezone('Asia/Jerusalem')),
                           days=MATCHDAYS,
                           context=TELEGRAM_CHAT_ID)

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
