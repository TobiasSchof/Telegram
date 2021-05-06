# standard library
from datetime import datetime, timedelta
from atexit import register, unregister
from configparser import ConfigParser
from tempfile import NamedTemporaryFile
from glob import glob
import os

# installs
from telethon import TelegramClient
import sqlite3
import telethon.sync # this relieves the need to use telethon as an asyncio library

config_file = "/Users/tobias/.Telegram_info.ini"
tel_scrape_path = os.path.join(os.path.expanduser("~"), "Telegram Scraper")

class TelegramError(Exception):
    pass

class NoMedia(Exception):
    pass

class EndRange(Exception):
    pass

class Scraper:
    """A class to scrape messages from a Telegram channels over a
        given date range

    NOTE: messages from a given channel that are posted within 1 second of
        each other will be considered the same message
    """

    def __init__(self, chnl, start, end, db=None, x_post_excl=[], dwnld_media=False):
        """Constructor
        
        NOTE: If using a sql database, a table "Scraper" will be created with the following collumns:
            (Channel TINYTEXT, ID INT UNSIGNED, Media TINYTEXT, Xpost TINYTEXT, DT DATETIME, Message MEDIUMTEXT, Comment TINYTEXT)
                Where Media is a comma separated list of the ids of any media attached to this message,
                      xpost is the channel name for the channel from which this post was crossposted from (if any),
                      DT is in utc

            Additionally, <tagname> BOOL columns (NULLable, default value False) will be added per tag 

        Args:
            chnl        = a string containing the telegram channel link (should look like t.me/example)
            start       = a datetime (with timezone) containing the earliest time for a telegram (inclusive)
            end         = a datetime (with timezone) containing the latest time for a telegram (inclusive)
            db          = the path of the database to use (or None for no database)
            x_post_excl = a list containing the channels to ignore crossposts from 
            dwnld_media = if True, will download the media to a permanent file (if False, will use temp file)
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

        # store variables
        self.start = start
        self.end = end
        self.db = db
        self.excl = x_post_excl if type(x_post_excl) is list else [x_post_excl]
        self.dwnld_media = dwnld_media

        # variables for holding message information
        self.msg = None
        self.comment = ""
        self.__loaded_comment = ""
        self.media = []
        if not self.dwnld_media:
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
        self.chnl = self.client.get_entity(chnl)

        # get first message in range
        try: first_id = self.client.get_messages(self.chnl, limit = 1, offset_date=self.start, reverse=True)[0].id
        except IndexError:
            raise EndRange("No messages on given channel in given range.")

        # if using database, load database
        if self.db is not None:
            # see if table exists
            try:
                # load database
                self.db = sqlite3.connect(self.db)
                #self.cur = self.db.cursor()
                # if database doesn't exist, make it
                self.db.execute("SELECT EXISTS ( SELECT 1 FROM Scraper )")
            # sqlite3 error
            except sqlite3.OperationalError as e:
                # if table doesn't exist, make it and move on
                if str(e).startswith("no such table"):
                    # make Scraper table
                    self.db.execute("CREATE TABLE Scraper (Channel TINYTEXT, ID INT UNSIGNED, Media TINYTEXT, xpost TINYTEXT, DT DATETIME, message MEDIUMTEXT, comment TINYTEXT)")
                    self.db.commit()
                # if it was a different error, throw it
                else: raise e
            # throw any other errors
            except Exception as e:
                raise e

        # load first message
        self.get_msg_by_id(first_id)

    def next(self):
        """Returns the next telegram in the date range
            (Will throw an error if this is the last telegram in the date range)
        """

        # check if id should be incremented from message or media
        if len(self.media) > 0:
            next_id = self.media[-1] + 1
        else:
            next_id = self.msg_id + 1

        try:
            return self.get_msg_by_id(next_id, expand=False)
        except EndRange:
            raise EndRange("Already at end of date range.")
        
    def prev(self):
        """Returns the previous telegram in the date range
            (Will throw an error if this is the first telegram in the date range)
        """

        try:
            return self.get_msg_by_id(self.msg_id - 1, expand=False)
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

        # check if media is already downloaded. Use glob because we don't know file type
        files = glob(os.path.join(tel_scrape_path, self.chnl.username, "{}.*".format(id)))
        # if glob found multiple possible files, raise an error
        if len(files) > 1:
            msg = "Found multiple possible files: "+("{}"*len(files)).format(*files)
            raise FileExistsError(msg)
        # if only one file, that's our file
        elif len(files) == 1:
            return files[0]

        # otherwise get message with media
        msg = self.client.get_messages(self.chnl, ids=id)
        if msg.media is None: raise NoMedia("No media for message {} on channel {}".format(id, self.chnl.username))

        if msg is None:
            raise EndRange("No message with id {} on channel {}.".format(id, self.chnl.username))

        # download media
        if self.dwnld_media:
            dir = os.path.join(tel_scrape_path, self.chnl.username)
            if not os.path.isdir(dir): os.mkdir(dir)
            fname = os.path.join(dir, str(id))
            self.client.download_media(msg, fname)
            # find actual file name (with extension)
            files = glob(os.path.join(tel_scrape_path, self.chnl.username, "{}.*".format(id)))
            # if glob found multiple possible files, raise an error
            if len(files) > 1:
                msg = "Found multiple possible files: "+("{}"*len(files)).format(*files)
                raise FileExistsError(msg)
            # if only one file, that's our file
            elif len(files) == 1:
                return files[0]
        else:
            print("download media file {}".format(id))
            self.client.download_media(msg, self.media_f.name)
            return self.media_f.name

    def get_msg_by_id(self, id, expand:bool = False):
        """Returns the telegram message by id in this channel, searching database first

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

        # if no database, just return the telegram loaded from the internet
        if self.db is None: return self.load_msg_from_telegram(id, expand=expand)

        # check if the current comment needs to be committed
        if self.__loaded_comment != self.comment:
            self.db.execute("UPDATE Scraper SET Comment = ? WHERE Channel = ? AND ID = ?", (self.comment,
                self.chnl.username, self.msg_id))
            self.db.commit()

        # check for entry in database
        msg = self.db.execute("SELECT * FROM Scraper WHERE Channel = ? AND ID = ?", (self.chnl.username, id)).fetchall()
        # if there's more than one entry, there's a problem with the database so inform the user
        if len(msg) > 1: raise sqlite3.DatabaseError("Database has more than one entry for message {} in channel {}.".format(id, self.chnl.username))
        # if there are no entries, load telegram
        elif len(msg) == 0:
            self.load_msg_from_telegram(id, expand = expand)
            # write information to database
            self.db.execute("INSERT INTO Scraper VALUES (?, ?, ?, ?, ?, ?, ?)", (self.chnl.username, 
                        self.msg_id, (("{},"*len(self.media))[:-1]).format(*self.media),
                        self.msg, "" if self.fwd is None else self.fwd, self.msg_date, ""))
            self.db.commit()
        else:
            dt = datetime.fromisoformat(msg[0][5])
            # check date range
            if expand:
                if dt > self.end:
                    self.end = dt
                if dt < self.start:
                    self.start = dt
            else:
                if dt > self.end or dt < self.start:
                    raise EndRange("Message {} out of date range.".format(id))

            # if we didn't raise an exception, load message from database
            self.msg_id = msg[0][1]
            self.media = [int(id) for id in msg[0][2].split(",") if id != ""]
            self.msg = msg[0][3]
            self.fwd = msg[0][4]
            self.msg_dat = dt
            self.comment = msg[0][6]
            # keep track of comment when it was loaded so we can tell if a commit to the database is necessary
            self.__loaded_comment = msg[0][6]

    def load_msg_from_telegram(self, id, expand:bool = False):
        """Loads a message from telegram
        
        Args:
            id:int      = the integer id of the message in the channel
            expand:bool = determines behavior if the message with the given
                            id is outside of the date range.
                            (if True, date range will be expanded to include this message,
                             if False, errors will be thrown)
        Returns:
            telethon.tl.patched.Message = the message at the given id
        """

        srch_msg = self.client.get_messages(self.chnl, ids=id) 
        # if there is no next message, throw error
        if srch_msg is None:
            raise EndRange("No message with id {} on channel {}.".format(id, self.chnl.username))
        
        # if the next message is later than the end of the date range, throw error
        if expand:
            if srch_msg.date > self.end:
                self.end = srch_msg.date
            if srch_msg.date < self.start:
                self.start = srch_msg.date
        else:
            if srch_msg.date > self.end or srch_msg.date < self.start:
                raise EndRange("Message {} out of date range.".format(id))

        # find channel this was forwarded from if it was a forward
        if srch_msg.forward is None:
            self.fwd = None
        else:
            self.fwd = srch_msg.forward.from_id.channel_id
            self.fwd = "t.me/"+self.client.get_entity(self.fwd).username

        # list to store ids for media
        self.media = []

        # search backwards if this message has no text
        old_msg = srch_msg
        if srch_msg.message == "":
            old_msg = srch_msg
            prev_msg = self.client.get_messages(self.chnl, ids=old_msg.id-1)

            while prev_msg is not None and prev_msg.message == "" and (old_msg.date - prev_msg.date) <= self.delt:
                if old_msg.media is not None: self.media.insert(0, old_msg.id)
                old_msg = prev_msg
                prev_msg = self.client.get_messages(self.chnl, ids=old_msg.id-1)

        # set our instance variables
        self.msg      = old_msg.message
        self.msg_id   = old_msg.id
        self.msg_date = old_msg.date
        if old_msg.media is not None: self.media.insert(0, old_msg.id)
        self.comment = ""

        # hold onto message to return it
        msg = old_msg

        # keep appending messages to media if they come in shortly
        #   and have no text
        old_msg = srch_msg
        next_msg = self.client.get_messages(self.chnl, ids=old_msg.id+1) 
        while next_msg is not None and next_msg.message == "" and (next_msg.date - old_msg.date) <= self.delt:
            if next_msg.media is not None: self.media.append(next_msg.id)
            old_msg = next_msg
            next_msg = self.client.get_messages(self.chnl, ids=old_msg.id+1) 

        return msg 

    def _cleanup(self, *ignored):
        """Will close connection to the telegram client,
            rendering further calls to methods invalid"""

        # disconnect from telegram client
        try: self.client.disconnect()
        except: pass

        self.client = None

        if not self.db is None:
            try:
                # check if the current comment needs to be committed
                if self.__loaded_comment != self.comment:
                    self.db.execute("UPDATE Scraper SET Comment = ? WHERE Channel = ? AND ID = ?", (self.comment,
                        self.chnl.username, self.msg_id))
                    self.db.commit()
            finally: self.db.close()

        try: unregister(self.close)
        except: pass

    def __iter__(self):
        """Method to turn this class into an iterator"""

        return self

    def __next__(self):
        """Method to turn this class into an iterator"""

        try: return self.next()
        except EndRange: raise StopIteration()