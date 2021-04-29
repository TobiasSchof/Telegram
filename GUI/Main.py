#!/usr/bin/env python

# inherent python libraries
from datetime import datetime, timezone
import sys, os

# installs
from PyQt5.QtWidgets import QApplication, QMainWindow, QDialog, QWidget, QVBoxLayout, QGroupBox, QLabel
from PyQt5.QtCore import Qt, QDateTime, QTimeZone, QSize
from PyQt5.QtGui import QMovie
from PyQt5 import uic
from googletrans import Translator

# project files
sys.path.append("/Users/tobias/Documents/Git/Telegram")
from Scraper import Scraper

# utc offset to get from QDateTimeEdit to UTC
#   (E.g. Belarus is UTC+3 so utcoffset of -3 is used here)
utcoffset = -3

# get path to resources folder
resource_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")

# Telegram Scraper folder
tel_scrape_path = os.path.join(os.path.expanduser("~"), "Telegram Scraper")

if not os.path.isdir(tel_scrape_path):
    print(tel_scrape_path)
    #os.mkdir(tel_scrape_path)

class Multi_Channel_Window(QDialog):
    """Widget for multi channel/date range selection

    NOTE: for now, this class is not used as single channel parsing
        was decided on for tagging
    """

    def __init__(self):
        """Constructor"""

        super().__init__()

        # load ui
        uic.loadUi(os.path.join(resource_path, "multi_setup_widget.ui"), self)

        # get ui for channels
        self.chnl_ui = os.path.join(resource_path, "channel_range_selection.ui")

        # make a list for channels
        chnl = QWidget()

        uic.loadUi(self.chnl_ui, chnl)
        chnl.rmv.clicked.connect(lambda _: self.rmv_chnl(chnl))

        self.chnls = [chnl]

        self.channels_list.setWidgetResizable(True)
        # turn off scroll bar on horizontal
        self.channels_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.channels_layout = QVBoxLayout()
        chnls_grp = QGroupBox()
        chnls_grp.setLayout(self.channels_layout)
        self.channels_list.setWidget(chnls_grp)

        self.channels_layout.addWidget(chnl)

        # this sets it so that horizontal scroll isn't possible
        chnls_grp.setMinimumWidth(chnl.minimumSizeHint().width())
        self.channels_list.setMinimumWidth(chnls_grp.minimumSizeHint().width())

        self.add.clicked.connect(self.add_chnl)
        self.load.clicked.connect(self.load_chnls)

    def add_chnl(self):
        """Adds a channel range"""

        # new widget
        chnl = QWidget()
        
        # load elements
        uic.loadUi(self.chnl_ui, chnl)

        # connect remove button
        chnl.rmv.clicked.connect(lambda _: self.rmv_chnl(chnl))

        # add to list
        self.chnls.append(chnl)

        # add to layout
        self.channels_layout.addWidget(chnl)

    def rmv_chnl(self, chnl):
        """Removes the given channel range"""

        chnl = self.chnls.pop(self.chnls.index(chnl))

        self.channels_layout.removeWidget(chnl)

        chnl.setParent(None)

    def load_chnls(self):
        """Loads the given info"""

        for chnl in self.chnls:
            load_telegram(chnl.chnl_name.text(),
                chnl.start_date.date(), chnl.start_date.time(),
                chnl.end_date.date(), chnl.end_date.time())

        self.close()

class Main(QMainWindow):

    def __init__(self):
        """Constructor"""

        super().__init__()

        self.media_idx = 0
        self.unscaled_img = None

        # load in ui
        uic.loadUi(os.path.join(resource_path, "Single_main_window.ui"), self)

        # set window title
        self.setWindowTitle("Telegram tagger")

        # instantiate scraper
        self.scraper = None
        # instantiate google translate helper
        self.translator = Translator()

        # add Qlabels to scroll areas for text
        self.orig_msg = QLabel("No messages for this channel in this date range.")
        self.orig_msg.setWordWrap(True)
        self.orig_msg.setAlignment(Qt.AlignTop)
        self.orig_msg.setMargin(10)
        self.orig_scroll.setWidget(self.orig_msg)
        self.trans_msg = QLabel("No messages for this channel in this date range.")
        self.trans_msg.setWordWrap(True)
        self.trans_msg.setAlignment(Qt.AlignTop)
        self.trans_msg.setMargin(10)
        self.trans_scroll.setWidget(self.trans_msg)

        # set end/start date range as the current time/date
        dt = datetime.now().astimezone(timezone.utc)
        dt = QDateTime.fromSecsSinceEpoch(dt.timestamp())
        dt = dt.toTimeZone(QTimeZone(60*60*3))
        self.date_from.setDateTime(dt)
        self.date_to.setDateTime(dt)

        # edits to channel or date range will create a new scraper
        self.chnl.editingFinished.connect(self.edit_scraper)
        self.date_from.editingFinished.connect(self.edit_scraper)
        self.date_to.editingFinished.connect(self.edit_scraper)

        # connect next and prev buttons for media
        self.prev_media_btn.clicked.connect(lambda _: self.load_media(self.media_idx-1))
        self.next_media_btn.clicked.connect(lambda _: self.load_media(self.media_idx+1))

        # connect next and prev buttons for message
        self.prev_msg_btn.clicked.connect(lambda _: (self.scraper.prev(), self.load_msg()))
        self.next_msg_btn.clicked.connect(lambda _: (self.scraper.next(), self.load_msg()))

        self.prev_msg_btn.setEnabled(False)
        self.next_msg_btn.setEnabled(False)

        # show GUI
        self.show()

    def edit_scraper(self):
        """Change the channel being parsed"""
        
        # convert dates to datetimes in utc
        start = self.date_from.dateTime()
        start = datetime(year = start.date().year(), month=start.date().month(), day=start.date().day(),
            hour = start.time().hour()+utcoffset, minute = start.time().minute(), second = start.time().second(),
            tzinfo=timezone.utc)
        end = self.date_to.dateTime()
        end = datetime(year = end.date().year(), month=end.date().month(), day=end.date().day(),
            hour = end.time().hour()+utcoffset, minute = end.time().minute(), second = end.time().second(),
            tzinfo=timezone.utc)
        # validate dates
        try: assert end <= datetime.now().astimezone(timezone.utc)
        except AssertionError:
            dt = datetime.now().astimezone(timezone.utc)
            end = dt
            dt = QDateTime.fromSecsSinceEpoch(dt.timestamp())
            dt = dt.toTimeZone(QTimeZone(60*60*3))
            self.date_to.setDateTime(dt)
        try: assert start <= end
        except AssertionError:
            self.date_from.setDateTime(self.date_to.dateTime()) 
            start = end

        # if this describes the current scraper, do nothing
        if self.scraper is not None:
            if self.scraper.start == start and self.scraper.end == end:
                if self.scraper.chnl_nm == self.chnl.text().split("/")[-1]: return

        # try to make scraper
        try: 
            # cleanup old scraper because telethon doesn't like two being signed in
            if self.scraper is not None: 
                self.scraper._cleanup()
                self.scraper = None
            self.scraper = Scraper(self.chnl.text(), start, end)
            self.chnl.setToolTip("The telegram channel to parse.")
            self.chnl.setStyleSheet("")
        except:
            self.chnl.setStyleSheet("background-color:red;")
            self.chnl.setToolTip("No messages for this channel in\nthe given date range.")
            self.chnl.setText("")

        self.load_msg()

    def load_msg(self):
        """Loads the message currently held by
            the scraper"""

        # clear messages if there's no valid scraper
        if self.scraper is None:
            self.orig_msg.setText("No messages for this channel in that date range")
            self.trans_msg.setText("No messages for this channel in that date range")
            self.msg_id.setText("")
            self.prev_msg_btn.setEnabled(False)
            self.next_msg_btn.setEnabled(False)
            return

        # otherwise set original text to message text
        self.orig_msg.setText(self.scraper.msg.message)

        # and try to translate
        try:
            trans = self.translator.translate(self.scraper.msg.message, src="ru")
            self.trans_msg.setText(trans.text)
        except Exception as e:
            print(e)
            self.trans_msg.setText("Error occurred with translation. Check internet connection.")

        # set message id box
        self.msg_id.setText("{}".format(self.scraper.msg.id))

        self.unscaled_img = None

        # disable next/prev message and media buttons if necessary
        try:
            self.scraper.prev()
            self.scraper.next()
            self.prev_msg_btn.setEnabled(True)
        except:
            self.prev_msg_btn.setEnabled(False)

        try:
            self.scraper.next()
            self.scraper.prev()
            self.next_msg_btn.setEnabled(True)
        except:
            self.next_msg_btn.setEnabled(False)

        if len(self.scraper.media) > 0:
            self.load_media(0)

    def load_media(self, idx):
        """Loads the media at the given idx from the scraper
            
        Args:
            idx = the index of the id in self.scraper.media to load.
                idx will be modded by the length of self.scraper.media
                so that media is loaded cyclicly by just incrementing
                idx (the caller doesn't have to keep track of when to
                reset the counter
        """

        # TODO: get placeholder image
        if self.scraper is None or len(self.scraper.media) == 0:
            self.prev_media_btn.setEnabled(False)
            self.next_media_btn.setEnabled(False)
            return

        try:
            if self.unscaled_img is None or self.media_idx != idx:
                self.media_f = self.scraper.get_media(self.scraper.media[idx%len(self.scraper.media)]) 

                # make a QMovie to display media
                _ = QMovie(self.media_f)
                _.jumpToFrame(0)
                self.unscaled_img = _.currentImage()

            # get aspect ratio
            scaled_size = self.unscaled_img.scaled(self.media_box.width(),
                        self.media_box.height(), Qt.KeepAspectRatio).size()


            # load new movie (scaling doesn't work once we jump to frame)
            movie = QMovie(self.media_f)
            # scale down
            movie.setScaledSize(scaled_size)
            self.media_box.setMovie(movie)
            movie.start()
            # set minimum size so we can scale back down
            self.media_box.setMinimumSize(QSize(1,1))
            self.media_idx = idx

            # disable buttons
            if len(self.scraper.media) == 1:
                self.prev_media_btn.setEnabled(False)
                self.next_media_btn.setEnabled(False)
            else:
                self.prev_media_btn.setEnabled(True)
                self.next_media_btn.setEnabled(True)

            # set media id
            self.media_id.setText("{}".format(self.scraper.media[idx%len(self.scraper.media)]))
        # load placeholder image
        except Exception as e: print(e)

    def resizeEvent(self, *args, **kwargs):
        """Implement resize event so we can reload image when window is made bigger"""

        super().resizeEvent(*args, **kwargs)

        self.load_media(self.media_idx)

if __name__ == "__main__":

    app = QApplication(sys.argv)
    widge = Main()
    sys.exit(app.exec_())