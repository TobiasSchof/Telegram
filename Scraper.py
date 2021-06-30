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

tel_scrape_path = os.path.join(os.path.expanduser("~"), "Documents", "Thesis")

class TelegramError(Exception):
    pass

class NoMedia(Exception):
    pass

class EndRange(Exception):
    pass

class XPostThrowaway(Exception):
    pass

class Scraper:
    """A class to scrape messages from a Telegram channels over a
        given date range

    NOTE: messages from a given channel that are posted within 1 second of
        each other will be considered the same message
    """

    def __init__(self, chnl, start, end, db=None, x_post_excl=[], dwnld_media=False, scrape_path=tel_scrape_path):
        """Constructor
        
        NOTE: If using a sql database, a table "Scraper" will be created. See the Readme for info on fields

        Args:
            chnl        = a string containing the telegram channel link (should look like t.me/example)
            start       = a datetime (with timezone) containing the earliest time for a telegram (inclusive)
            end         = a datetime (with timezone) containing the latest time for a telegram (inclusive)
            db          = the path of the database to use (or None for no database)
            x_post_excl = a list containing the channels to ignore crossposts from 
            dwnld_media = if True, will download the media to a permanent file (if False, will use temp file)
            scrape_path = the directory that this scraper should work out of
                            (this is where media will be saved, the session will be saved, etc.)
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
        if type(x_post_excl) is not list: x_post_excl = [x_post_excl]
        if len([chnl for chnl in x_post_excl if not chnl.startswith("t.me/")]) > 0:
            raise ValueError("All excluded channels should be the full username beginning with t.me/")

        # check path
        if not os.path.isdir(scrape_path):
            try: os.mkdir(scrape_path)
            except: raise FileNotFoundError("Error creating path '{}'. Every directory except last must already exist.".format(scrape_path))
        self.scrape_path = scrape_path

        # setup cleanup method
        register(self._cleanup)

        # the time delta in which media is considered an extension of a message
        self.delt = timedelta(seconds = 1)

        # store variables
        self.start = start
        self.end = end
        self.db = db
        self.excl = [chnl.lower() for chnl in x_post_excl]
        self.dwnld_media = dwnld_media

        # variables for holding message information
        self.msg = None
        self.comment = ""
        self.__loaded_comment = ""
        self.media = []
        self.tags = {}
        if not self.dwnld_media:
            self.media_f = NamedTemporaryFile()

        # get info for telegram client
        cf = ConfigParser()
        cf.read(os.path.join(self.scrape_path, ".Telegram_info.ini"))
        api_id = cf.getint("Thesis", "api_id")
        api_hash = cf.get("Thesis", "api_hash")

        # connect to telegram
        #   note, validation takes a second so we keep the client open
        #   as long as the class is alive (closed on exit)
        self.client = TelegramClient(os.path.join(self.scrape_path, "scraper.session"), api_id, api_hash)
        # authenticate (will use input if necessary)
        self.client.start()
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
                    self.db.execute("CREATE TABLE Scraper (Channel TINYTEXT, ID INT UNSIGNED, Media TINYTEXT, xpost TINYTEXT, DT DATETIME, message MEDIUMTEXT, Silent BOOL, Legacy BOOL, Edt_hid BOOL, Pinned BOOL, Bot_id INT UNSIGNED, Reply_to TINYTEXT, Views INT UNSIGNED, Forwards INT UNSIGNED, Replies INT UNSIGNED, edt_dt DATETIME, comment TINYTEXT)")
                    self.db.commit()
                # if it was a different error, throw it
                else: raise e
            # throw any other errors
            except Exception as e:
                raise e

        # load first message
        while True:
            try:
                self.get_msg_by_id(first_id)
                break
            except XPostThrowaway:
                first_id += 1
                self.get_msg_by_id(first_id)
            except EndRange:
                raise EndRange("No messages that aren't crossposts form the listed channels in the date range.")

    def next(self):
        """Returns the next telegram in the date range
            (Will throw an error if this is the last telegram in the date range)
        """

        # check if id should be incremented from message or media
        if len(self.media) > 0:
            next_id = self.media[-1] + 1
        else:
            next_id = self.msg_id + 1

        # keep trying until we either find one that isn't an excluded crosspost
        #   or EndRange is thrown
        while True:
            try:
                return self.get_msg_by_id(next_id, expand=False)
            except EndRange as e:
                # in this case, the message is missing. But it seems that sometimes,
                #   that doesn't mean we're done so try for another 30 messages
                #   (ran into a 20 message break on nexta_live)
                if str(e).startswith("No message with id"):
                    id = next_id + 1
                    while id - next_id <= 30:
                        try:
                            msg = self.get_msg_by_id(id, expand=False)
                            return msg
                        except: pass
                        id += 1

                    if id - next_id > 15:
                        raise EndRange("Already at end of date range.")
                else:
                    raise EndRange("Already at end of date range.")
            except XPostThrowaway: next_id += 1
        
    def prev(self):
        """Returns the previous telegram in the date range
            (Will throw an error if this is the first telegram in the date range)
        """

        prev_id = self.msg_id - 1

        # keep trying until we either find one that isn't an excluded crosspost
        #   or EndRange is thrown
        while True:
            try:
                return self.get_msg_by_id(prev_id, expand=False)
            except EndRange as e:
                # in this case, the message is missing. But it seems that sometimes,
                #   that doesn't mean we're done so try for another 30 messages
                #   (ran into a 20 message break on nexta_live)
                if str(e).startswith("No message with id"):
                    id = prev_id - 1
                    while prev_id - id <= 30:
                        try:
                            msg = self.get_msg_by_id(id, expand=False)
                            return msg
                        except: pass
                        id -= 1

                    if prev_id - id > 15:
                        raise EndRange("Already at end of date range.")
                else:
                    raise EndRange("Already at end of date range.")
            except XPostThrowaway: prev_id -= 1

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
        files = glob(os.path.join(self.scrape_path, self.chnl.username, "{}.*".format(id)))
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
            dir = os.path.join(self.scrape_path, self.chnl.username)
            if not os.path.isdir(dir): os.mkdir(dir)
            fname = os.path.join(dir, str(id))
            self.client.download_media(msg, fname)
            # find actual file name (with extension)
            files = glob(os.path.join(self.scrape_path, self.chnl.username, "{}.*".format(id)))
            # if glob found multiple possible files, raise an error
            if len(files) > 1:
                msg = "Found multiple possible files: "+("{}"*len(files)).format(*files)
                raise FileExistsError(msg)
            # if only one file, that's our file
            elif len(files) == 1:
                return files[0]
        else:
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

        # check if any tags need to be updated
        try: self.commit_tags()
        # attribute error if no database or if no message loaded
        except: pass

        # check for entry in database
        msg = self.db.execute("SELECT * FROM Scraper WHERE Channel = ? AND ID = ?", (self.chnl.username, str(id))).fetchall()
        # if there's more than one entry, there's a problem with the database so inform the user
        if len(msg) > 1: raise sqlite3.DatabaseError("Database has more than one entry for message {} in channel {}.".format(id, self.chnl.username))
        # if there are no entries, load telegram
        elif len(msg) == 0:
            # check if this id is media associated to another id
            # if media is in middle
            msg = self.db.execute("SELECT * FROM Scraper WHERE Channel = ? AND Media LIKE ?", (self.chnl.username, '%,'+str(id)+',%')).fetchall()
            # if multiple responses
            if len(msg) > 1: raise sqlite3.DatabaseError("ID {} in channel {} seems be me associated to multiple messages.".format(id, self.chnl.username))
            # if no responses
            elif len(msg) == 0:
                self.load_msg_from_telegram(id, expand = expand)
                # write information to database
                self.db.execute("INSERT INTO Scraper (Channel, ID, Media, Xpost, DT, Message, Silent, Legacy, Edt_hid, Pinned, Bot_id, Reply_to, Views, Forwards, Replies, edt_dt, Comment) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (self.chnl.username, self.msg_id,
                            ((",{}"*len(self.media))+",").format(*self.media),
                            "" if self.fwd is None else self.fwd, self.msg_date,
                            self.msg, self.silent, self.legacy,
                            self.edit_hide, self.pinned, self.bot_id,
                            "{},{}".format(self.reply_channel, self.reply_msg_id),
                            self.views, self.fwds, self.replies,
                            self.edit_date, self.comment))
                self.db.commit()
                self.load_tags()
                return
            # if one, just use that entry

        dt = datetime.fromisoformat(msg[0][4])
        # check date range
        if expand:
            if dt > self.end:
                self.end = dt
            if dt < self.start:
                self.start = dt
        else:
            if dt > self.end or dt < self.start:
                raise EndRange("Message {} out of date range.".format(id))

        # check for crosspost to be excluded
        fwd = msg[0][3].lower()
        if fwd.lower() in self.excl:
            msg = "Crosspost from {}".format(fwd)
            raise XPostThrowaway(msg)

        # if we didn't raise an exception, load message from database
        self.msg_id = msg[0][1]
        self.media = [int(id) for id in msg[0][2].split(",") if id != ""]
        self.msg = msg[0][5]
        self.fwd = fwd
        self.msg_dat = dt
        self.silent = msg[0][6]
        self.legacy = msg[0][7]
        self.edit_hide = msg[0][8]
        self.pinned = msg[0][9]
        self.bot_id = msg[0][10]
        reply_info = msg[0][11].split(",")
        self.reply_channel = None if reply_info[0].lower() == "none" else reply_info[0]
        self.reply_msg_id = None if reply_info[1].lower() == "none" else int(reply_info[1])
        self.views = msg[0][12]
        self.fwds = msg[0][13]
        self.replies = msg[0][14]
        self.edit_date = datetime.fromisoformat(msg[0][15]) if msg[0][15] is not None else None
        self.comment = msg[0][16]
        # keep track of comment when it was loaded so we can tell if a commit to the database is necessary
        self.__loaded_comment = msg[0][6]
        self.load_tags()

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

        # list to store ids for media
        self.media = []

        # search backwards if this message has no text
        old_msg = srch_msg
        if srch_msg.message == "":
            old_msg = srch_msg
            prev_msg = self.client.get_messages(self.chnl, ids=old_msg.id-1)

            while prev_msg is not None and (old_msg.date - prev_msg.date) <= self.delt:
                if old_msg.media is not None: self.media.insert(0, old_msg.id)
                old_msg = prev_msg
                if old_msg.message != "": break
                prev_msg = self.client.get_messages(self.chnl, ids=old_msg.id-1)

        # find channel this was forwarded from if it was a forward
        if srch_msg.forward is None:
            self.fwd = None
        else:
            fwd = srch_msg.forward.from_id.channel_id
            try:
                fwd = "t.me/"+self.client.get_entity(fwd).username
                if fwd.lower() in self.excl:
                    msg = "Crosspost from {}".format(fwd)
                    raise XPostThrowaway(msg)
                self.fwd = fwd
            except telethon.errors.rpcerrorlist.ChannelPrivateError:
                fwd = None
                self.fwd = None

        # find channel this is a reply to if was a reply
        if srch_msg.reply_to is None:
            self.reply_channel = None
            self.reply_msg_id = None
        else:
            if srch_msg.reply_to.reply_to_peer_id is None:
                self.reply_channel = None
            else:
                try:
                    self.reply_channel = "t.me/"+self.client.get_entity(srch_msg.reply_to.reply_to_peer_id).username
                except telethon.errors.rpcerrorlist.ChannelPrivateError:
                    self.reply_channel = None
            self.reply_msg_id = srch_msg.reply_to.reply_to_msg_id

        # set our instance variables
        self.msg       = old_msg.message
        self.silent    = old_msg.silent
        self.legacy    = old_msg.legacy
        self.edit_hide = old_msg.edit_hide
        self.pinned    = old_msg.pinned
        self.bot_id    = old_msg.via_bot_id
        self.views     = old_msg.views
        self.fwds      = old_msg.forwards
        self.replies   = old_msg.replies
        self.edit_date = old_msg.edit_date
        self.msg_id    = old_msg.id
        self.msg_date  = old_msg.date
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

    def add_tag(self, tag_nm, def_val=False):
        """Adds a tag to the database

        Args:
            tag_nm = what the tag should be called
            def_val = the default value that should be applied to the column
        """

        if tag_nm in self.tags:
            raise ValueError("'{}' is already a tag.".format(tag_nm))

        cmd = "ALTER TABLE Scraper ADD COLUMN '{}' BOOL DEFAULT {}".format(tag_nm, def_val)
        try:
            self.db.execute(cmd)
            self.db.commit()
            self.tags[tag_nm] = def_val
        except Exception as e:
            if str(e).startswith("duplicate column name"):
                raise ValueError("'{}' is already a tag.".format(tag_nm))
            else: raise e

    def load_tags(self):
        """Load tags from the database"""

        # get the name of all tags
        all_tags = self.db.execute("PRAGMA table_info(Scraper)").fetchall()[17:]
        # get the entry for this message in the database
        entry = self.db.execute("SELECT * FROM Scraper WHERE Channel = ? AND ID = ?", (self.chnl.username, str(self.msg_id))).fetchall()
        # make sure there's exactly one entry
        if len(entry) > 1: raise sqlite3.DatabaseError("ID {} in channel {} seems be me associated to multiple messages.".format(self.msg_id, self.chnl.username))
        if len(entry) == 0: raise sqlite3.DatabaseError("No database entry for {} in channel {}".format(self.msg_id, self.chnl.username))
        entry = entry[0]

        # clear tags dictionary
        self.tags = {}
        # iterate through tags, store value
        for tag in all_tags:
            self.tags[tag[1]] = bool(entry[tag[0]])

    def commit_tags(self):
        """A method to commit any tags that need to be committed to the database"""

        if self.db is None: raise AttributeError("No database backing on this scraper.")

        # pull current database tags into temporary dictionary

        # check that all tags in self.tags are in database
        all_tags = self.db.execute("PRAGMA table_info(Scraper)").fetchall()[7:]
        to_add = [tag for tag in self.tags if tag not in all_tags]

        # add any tags to database that aren't already there
        if len(to_add) > 0:
            for tag in to_add:
                cmd = "ALTER TABLE Scraper ADD COLUMN '{}' BOOL DEFAULT {}".format(tag, False)
                try:
                    self.db.execute(cmd)
                    self.db.commit()
                except: pass

        # get the entry for this message in the database
        entry = self.db.execute("SELECT * FROM Scraper WHERE Channel = ? AND ID = ?", (self.chnl.username, str(self.msg_id))).fetchall()
        # make sure there's exactly one entry
        if len(entry) > 1: raise sqlite3.DatabaseError("ID {} in channel {} seems be me associated to multiple messages.".format(self.msg_id, self.chnl.username))
        if len(entry) == 0: raise sqlite3.DatabaseError("No database entry for {} in channel {}".format(self.msg_id, self.chnl.username))
        entry = entry[0]

        # make database tags dict
        db_tags = {}
        # iterate through tags, store value
        for tag in all_tags:
            db_tags[tag[1]] = bool(entry[tag[0]])

        # find difference
        edits = {tag:self.tags[tag] for tag in self.tags if self.tags[tag] != db_tags[tag]} 

        if len(edits) == 0: return

        # edit table with differences
        for tag in edits:
            cmd = "UPDATE Scraper SET '{}' = ? WHERE CHANNEL = ? AND ID = ?".format(tag)
            self.db.execute(cmd, (self.tags[tag], self.chnl.username, self.msg_id))
        
        # commit change
        self.db.commit()

    def _cleanup(self, *ignored):
        """Will close connection to the telegram client,
            rendering further calls to methods invalid"""

        # disconnect from telegram client
        try: self.client.disconnect()
        except: pass

        # disconnect from client so session db closes
        try:
            self.client.disconnect()
            self.client = None
        except: pass

        if not self.db is None:
            try:
                # check if the current comment needs to be committed
                if self.__loaded_comment != self.comment:
                    self.db.execute("UPDATE Scraper SET Comment = ? WHERE Channel = ? AND ID = ?", (self.comment,
                        self.chnl.username, self.msg_id))
                    self.db.commit()
                # commit tags if necessary
                self.commit_tags()
            except: pass
            finally:
                if self.db is not None and type(self.db) is not str:
                    self.db.close()

        try: unregister(self.close)
        except: pass

    def __iter__(self):
        """Method to turn this class into an iterator"""

        return self

    def __next__(self):
        """Method to turn this class into an iterator"""

        try: return self.next()
        except EndRange: raise StopIteration()