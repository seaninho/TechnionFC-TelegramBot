import os

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
TELEGRAM_GROUP_INVITE_LINK = os.environ.get('TELEGRAM_GROUP_INVITE_LINK', '')
PORT = int(os.environ.get('PORT', 8443))