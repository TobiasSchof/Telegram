from astropy.io import fits
from telethon import TelegramClient
from datetime import datetime, timedelta
from atexit import register, unregister
from configparser import ConfigParser
from tempfile import NamedTemporaryFile
import telethon.sync # this relieves the need to use telethon as an asyncio library
import os

config_file = "/Users/tobias/.Telegram_info.ini"

class TelegramError(Exception):
    pass

class EndRange(Exception):
    pass

class Scraper:
    """A class to scrape messages from a Telegram channels over a
        given date range

    NOTE: messages from a given channel that are posted within 1 second of
        each other will be considered the same message
    """

    def __init__(self, chnl, start, end):
        """Constructor
        
        Args:
            chnl  = a string containing the telegram channel link (should look like t.me/example)
            start = a datetime (with timezone) containing the earliest time for a telegram (inclusive)
            end   = a datetime (with timezone) containing the latest time for a telegram (inclusive)
        """

        # validate input
        if not type(chnl) is str:
            raise ValueError("Channel name should be a string")
        if not chnl[:5] == "t.me/":
            raise ValueError("Channel name should start with 't.me/'")
        if not type(start) is datetime or not type(end) is datetime:
            raise ValueError("Start and end must be datetimes")
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("Start and end should have timezones")
        if not start <= end:
            raise ValueError("Start must be earlier than (or the same time as) end")

        # setup cleanup method
        register(self._cleanup)

        # the time delta in which media is considered an extension of a message
        self.delt = timedelta(seconds = 1)

        self.ids = []
        self.telegrams = {}

        self.chnl_nm = chnl.split("/")[-1]
        self.start = start
        self.end = end

        self.msg = None
        self.media = []
        self.media_f = NamedTemporaryFile()

        # get info for telegram client
        cf = ConfigParser()
        cf.read(config_file)
        api_id = cf.getint("Thesis", "api_id")
        api_hash = cf.get("Thesis", "api_hash")

        # connect to telegram
        #   note, validation takes a second so we keep the client open
        #   as long as the class is alive (closed on exit)
        self.client = TelegramClient('scraper', api_id, api_hash)
        self.client.connect()
        self.chnl = self.client.get_entity(self.chnl_nm)

        # get first message in range
        try: first_id = self.client.get_messages(self.chnl, limit = 1, offset_date=self.start, reverse=True)[0].id
        except IndexError:
            raise EndRange("No messages on given channel in given range.")

        self.get_msg_by_id(first_id)

    def next(self):
        """Returns the next telegram in the date range
            (Will throw an error if this is the last telegram in the date range)
        """

        # check if id should be incremented from message or media
        if len(self.media) > 0:
            next_id = self.media[-1] + 1
        else:
            next_id = self.msg.id + 1

        try:
            return self.get_msg_by_id(next_id, expand=False)
        except:
            raise EndRange("Already at end of date range.")
        
    def prev(self):
        """Returns the previous telegram in the date range
            (Will throw an error if this is the first telegram in the date range)
        """

        try:
            return self.get_msg_by_id(self.msg.id - 1, expand=False)
        except EndRange:
            raise EndRange("Already at beginning of date range.")

    def get_media(self, id):
        """Downloads the media attached to message with the given id as
            a temporary named file

        Args:
            id:int = the id of the message to fetch media for
        Returns:
            str = the filepath to the downloaded file
        """

        if self.client is None: return

        try: id = int(id)
        except:
            raise ValueError("id must be an integer")

        # get message with media
        msg = self.client.get_messages(self.chnl, ids=id)

        if msg is None:
            raise EndRange("No message with id {} on channel {}.".format(id, self.chnl_nm))

        # download media
        self.client.download_media(msg, self.media_f.name)

        return self.media_f.name

    def get_msg_by_id(self, id, expand:bool = True):
        """Returns the telegram message by id in this channel

        Args:
            id:int      = the integer id of the message in the channel
            expand:bool = determines behavior if the message with the given
                            id is outside of the date range.
                            (if True, date range will be expanded to include this message,
                             if False, errors will be thrown)
        Returns:
            telethon.tl.patched.Message = the message at the given id
        """

        if self.client is None: return

        try: id = int(id)
        except:
            raise ValueError("id must be an integer")

        srch_msg = self.client.get_messages(self.chnl, ids=id) 
        # if there is no next message, throw error
        if srch_msg is None:
            raise EndRange("No message with id {} on channel {}.".format(id, self.chnl_nm))
        
        # if the next message is later than the end of the date range, throw error
        if not expand:
            if srch_msg.date > self.end or srch_msg.date < self.start:
                raise EndRange("Message {} out of date range.".format(id))
        else:
            if srch_msg.date > self.end:
                self.end = srch_msg.date
            if srch_msg.date < self.start:
                self.start = srch_msg.date

        self.media = []

        # search backwards if this message has no text
        old_msg = srch_msg
        if srch_msg.message == "":
            old_msg = srch_msg
            prev_msg = self.client.get_messages(self.chnl, ids=old_msg.id-1)

            while prev_msg is not None and (old_msg.date - prev_msg.date) <= self.delt:
                if old_msg.media is not None: self.media.insert(0, old_msg.id)
                old_msg = prev_msg
                # if message is not empty, it's a head
                if prev_msg.message != "": break 
                # otherwise, keep searching
                else: prev_msg = self.client.get_messages(self.chnl, ids=old_msg.id-1)

        # set our head
        self.msg = old_msg

        # add this message's media 
        if self.msg.media is not None: self.media.insert(0, self.msg.id)

        # keep appending messages to media if they come in shortly
        #   and have no text
        old_msg = srch_msg
        next_msg = self.client.get_messages(self.chnl, ids=old_msg.id+1) 
        while next_msg is not None and (next_msg.date - old_msg.date) <= self.delt and next_msg.message=="":
            self.media.append(next_msg.id)
            old_msg = next_msg
            next_msg = self.client.get_messages(self.chnl, ids=old_msg.id+1) 

        return self.msg

    def _cleanup(self, *ignored):
        """Will close connection to the telegram client,
            rendering further calls to methods invalid"""

        # disconnect from telegram client
        try: self.client.disconnect()
        except: pass

        self.client = None

        try: unregister(self.close)
        except: pass