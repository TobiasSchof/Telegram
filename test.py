from telethon import TelegramClient
import telethon.sync
from datetime import datetime
from astropy.io import fits
from configparser import ConfigParser

cf = ConfigParser()
cf.read("/Users/tobias/.Telegram_info.ini")

# (1) Use your own values here
api_id = cf.getint("Thesis", "api_id")
api_hash = cf.get("Thesis", "api_hash")

username = 'scraper'

# (2) Create the client and connect
client = TelegramClient(username, api_id, api_hash)

with client:
    # Ensure you're authorized
    if not client.is_user_authorized():
        print("Not authorized")
    else:
        # conversations and joined channels
        #dialogs = client.get_dialogs()
        #for dialog in dialogs:
        #    print(dialog.title)
        channel = client.get_entity("NEXTA_TV")
        # date to parse
        dt = datetime(2021, 3, 8, 0, 0, 0)
        # start at date
        try:
            message = client.get_messages(channel, limit=1, offset_date=dt, reverse=True)[0]
        except IndexError:
            print("No messages since {}/{}/{}".format(dt.month, dt.day, dt.year))

        while message.date.date() == dt.date():
            print("message {}:".format(message.id))
            print()
            print(str(message))
            print()
            #if x.media is not None:
            #    print("downloading media")
            #    x.download_media("/tmp/Telegram_media_for_file_{}".format(x.id))
            print("---"*45)
            message = client.get_messages(channel, ids=(message.id+1))
            if message is None:
                break

        print("done with parsing {}/{}/{}".format(dt.month, dt.day, dt.year))
        if message is not None:
            print("First message not processed: id - {} date/time - {}/{}/{} {}:{}:{}".format(message.id,
                message.date.month, message.date.day, message.date.year, message.date.hour,
                message.date.minute, message.date.second))
        else: print("Last message query returned None.")
