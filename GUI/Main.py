#!/usr/bin/env python

# inherent python libraries
from datetime import datetime, timezone, timedelta
from configparser import ConfigParser
from glob import glob
from functools import partial
import sys, os, math

# installs
from PyQt5.QtWidgets import (QApplication, QMainWindow, QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
    QGroupBox, QLabel, QFileDialog, QToolButton, QLineEdit, QStyle, QSlider, QInputDialog, QMessageBox,
    QGridLayout, QCheckBox, QAction, QScrollArea, QComboBox, QPushButton)
from PyQt5.QtCore import Qt, QSize, QUrl, QCoreApplication
from PyQt5.QtGui import QMovie, QIntValidator, QIcon
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5 import uic
from google.cloud import translate_v2 as translate
from telethon import TelegramClient

# project files
sys.path.append(os.path.normpath(os.path.abspath(__file__) + (os.sep + os.pardir) * 2))
from Scraper import Scraper, EndRange, NoMedia, XPostThrowaway
import resources.images

# utc offset to get from QDateTimeEdit to UTC
#   (E.g. Belarus is UTC+3 so utcoffset of -3 is used here)
utcoffset = -3

# get path to resources folder
resource_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")

# Telegram Scraper folder
tel_scrape_path = os.path.join(os.path.expanduser("~"), "Documents", "Thesis")

if not os.path.isdir(tel_scrape_path):
    os.mkdir(tel_scrape_path)

class Settings_window(QDialog):
    """A widget to hold information about the scraper's settings"""

    def __init__(self, *args, **kwargs):
        """Constructor"""

        super().__init__(*args, **kwargs)

        # load ui
        uic.loadUi(os.path.join(resource_path, "settings_window.ui"), self)

        self.x_posts_area.setWidgetResizable(True)
        # turn off scroll bar on horizontal
        self.x_posts_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # setup scroll area layout
        self.x_post_layout = QVBoxLayout()
        self.chnls_grp = QGroupBox()
        self.chnls_grp.setLayout(self.x_post_layout)
        self.x_posts_area.setWidget(self.chnls_grp)

        # setup entries in scroll area
        self.excludes = []
        self.parse()

        # make sure minimum size is set (to stop horizontal scrolling)
        self.chnls_grp.setMinimumWidth(self.x_post_layout.itemAt(0).widget().minimumSizeHint().width())
        self.x_posts_area.setMinimumWidth(self.chnls_grp.minimumSizeHint().width())

        # get db info fields
        self.db_path = self.db_group.findChild(QLineEdit, "db_loc")
        self.db_edit = self.db_group.findChild(QToolButton, "db_edit")
        # connect db edit button
        self.db_edit.clicked.connect(self.edit_db_loc)

        # if a session file exists, use it
        if os.path.isfile(os.path.join(tel_scrape_path, "session.ini")):
            cf = ConfigParser()
            cf.read(os.path.join(tel_scrape_path, "session.ini"))

            # set channel name
            self.chnl.setText("t.me/"+cf["Scraper"]["chnl"])

            # set date range
            start = datetime.fromisoformat(cf["Scraper"]["start"])
            end = datetime.fromisoformat(cf["Scraper"]["end"])
            self.date_from.setDateTime(start)
            self.date_to.setDateTime(end)

            # set database location
            self.db_path.setText(cf["Settings"]["db_loc"])

            # set save media button
            self.media_sv.setChecked(cf["Settings"]["sv_media"] == "True")

            # set excludes
            excludes = cf["Settings"]["excludes"].split("|")
            # add excludes to widget list
            for excl in excludes:
                if excl != "":
                    # make a new widget
                    widge = QWidget()
                    # load ui
                    uic.loadUi(os.path.join(resource_path, "x_post_item.ui"), widge)
                    # connect delete button
                    rmv = lambda : (self.x_post_layout.removeWidget(widge),
                                    widge.setParent(None),
                                    self.parse())
                    # set text
                    widge.chnl_nm.setText(excl)
                    # lambda function for parsing after text edit
                    chng = lambda : self.parse()
                    widge.dlt_btn.clicked.connect(rmv)
                    # connect editingFinished in qlabel
                    widge.chnl_nm.editingFinished.connect(chng)
                    # add it to the scroll area
                    self.x_post_layout.addWidget(widge)
            # parse excludes
            self.parse()
        else:
            # check if there are any databases in default location
            dbs = glob(os.path.join(tel_scrape_path, "*.db"))
            if len(dbs) > 0: self.db_path.setText(dbs[0])
            else: self.db_path.setText(os.path.join(tel_scrape_path, "Project1.db"))

    def parse(self):
        """A method to parse all the cross post items"""

        self.excludes = []
        removes = []
        for idx in range(0, self.x_post_layout.count()):
            # get widget
            widge = self.x_post_layout.itemAt(idx).widget()
            # if we find a blank channel, add it to the list of widgets to remove
            if widge.chnl_nm.text() == "": removes.insert(0, idx)
            else:
                # if channel name doesn't start with t.me/, prepend it
                if not widge.chnl_nm.text().startswith("t.me/"):
                    widge.chnl_nm.setText("t.me/{}".format(widge.chnl_nm.text()))
                # add to list to exclude
                self.excludes.append(widge.chnl_nm.text())

        # if last field is not blank, make it so
        if len(removes) == 0 or removes[-1] != self.x_post_layout.count() -1:
            # make a new widget
            widge = QWidget()
            # load ui
            uic.loadUi(os.path.join(resource_path, "x_post_item.ui"), widge)
            # connect delete button
            rmv = lambda : (self.x_post_layout.removeWidget(widge),
                            widge.setParent(None),
                            self.parse())
            # lambda function for parsing after text edit
            chng = lambda : self.parse()
            widge.dlt_btn.clicked.connect(rmv)
            # connect editingFinished in qlabel
            widge.chnl_nm.editingFinished.connect(chng)
            # add it to the scroll area
            self.x_post_layout.addWidget(widge)
        # otherwise, don't remove last element
        else: removes.pop(-1)

        # remove blank elements. Remove is decreasing, so we don't need
        #   to worry about indexes changing as we remove elements
        for idx in removes:
            w = self.x_post_layout.itemAt(idx).widget()
            # disconnect slots
            w.dlt_btn.clicked.disconnect()
            w.chnl_nm.editingFinished.disconnect()
            # disconnect from parent
            w.setParent(None)
            # clear from layout
            self.x_post_layout.removeWidget(w)

    def edit_db_loc(self):
        """Method that's called when the edit db button is pressed"""

        filedialog = QFileDialog(self)
        # set to select save file
        filedialog.setAcceptMode(QFileDialog.AcceptOpen)
        # set filter to only show .db files
        filedialog.setNameFilters(["Databases (*.db)", "All files (*.*)"])
        filedialog.selectNameFilter("Databases (*.db)")
        # set default directory
        filedialog.setDirectory(tel_scrape_path)
        
        # if window was accepted
        if (filedialog.exec()):
            # pull filename
            filename = filedialog.selectedFiles()[0]
            self.db_path.setText(filename)

    def keyPressEvent(self, evt):
        """Override keyPressEvent to not close dialog box w/ enter"""

        # if key was enter or return, return
        if(evt.key() == Qt.Key_Enter or evt.key() == Qt.Key_Return): return
        # otherwise, behave normally
        super().keyPressEvent(evt)

class Filter_window(QDialog):
    """A class to handle filters"""

    def __init__(self, main_window, *args, **kwargs):
        """Constructor"""

        super().__init__(*args, **kwargs)

        # load ui
        uic.loadUi(os.path.join(resource_path, "Filter_window.ui"), self)
        
        # get hook to main widget so we can get scraper
        self.main = main_window

        # hold filter tags
        self.tags = []
        # hold tag widgets
        self.tag_widgs = {}

        # set up scroll area
        self.scroll_area = self.findChildren(QScrollArea)[0]
        self.filters = QGroupBox()
        self.scroll_area.setWidget(self.filters)
        self.filters.setLayout(QVBoxLayout())

        self.add_section = QWidget()
        self.add_section.setLayout(QHBoxLayout())
        self.add_section_tag = QComboBox()
        self.add_section_btn = QPushButton("add")
        self.add_section_btn.clicked.connect(self.add_tag)
        self.add_section.layout().addWidget(self.add_section_tag)
        self.add_section.layout().addWidget(self.add_section_btn)
        self.add_section.layout().setStretch(0, 5)
        self.add_section.layout().setStretch(1, 1)

        self.filters.layout().addWidget(self.add_section)

        # populate self
        self.parse_tags()

    def parse_tags(self):
        """A method to setup the tag box"""

        # if there's no scraper, erase the filter
        if self.main.scraper is None:
            for nm, widg in self.tag_widgs.items():
                widg.setParent(None)
            self.tag_widgs = {}
            return

        # otherwise, delete the tags that need to be deleted
        for nm, widg in self.tag_widgs.copy().items():
            if nm not in self.main.scraper.tags:
                _ = self.tag_widgs.pop(nm)
                widg.setParent(None)

        self.add_section_tag.clear()
        for tag, val in self.main.scraper.tags.items():
            self.add_section_tag.addItem(tag)

    def add_tag(self):
        """Method to add a tag"""

        tag = self.add_section_tag.currentText()
        if tag not in self.tag_widgs:
            self.tag_widgs[tag] = QWidget()
            uic.loadUi(os.path.join(resource_path, "filter_tag.ui"), self.tag_widgs[tag])
            self.tag_widgs[tag].tag_str.setText(tag)
            self.tag_widgs[tag].trash.clicked.connect(partial(self.remove_filter, tag))
            self.filters.layout().insertWidget(0, self.tag_widgs[tag])

    def remove_filter(self, tag):
        """Method to remove the filter on <tag>"""

        if not tag in self.tag_widgs: return

        widg = self.tag_widgs.pop(tag)
        widg.setParent(None)

    def exec_(self, *args):
        """Catch execute to copy tags, widgets and then revert/keep changes
            depending on cancel/ok button"""

        self.parse_tags()

        tags = {nm : widg.tag_val.currentIndex() for nm, widg in self.tag_widgs.items()}

        ret = super().exec_(*args)

        # if accepted, continue
        if ret:
            return ret
        # otherwise, reset widgets
        else:
            for tag, widg in self.tag_widgs.copy().items():
                _ = self.tag_widgs.pop(tag)
                widg.setParent(None)
            for tag, val in tags.items():
                self.tag_widgs[tag] = QWidget()
                uic.loadUi(os.path.join(resource_path, "filter_tag.ui"), self.tag_widgs[tag])
                self.tag_widgs[tag].tag_str.setText(tag)
                self.tag_widgs[tag].tag_val.setCurrentIndex(val)
                self.tag_widgs[tag].trash.clicked.connect(partial(self.remove_filter, tag))
                self.filters.layout().insertWidget(0, self.tag_widgs[tag]) 

class Media_Player(QWidget):
    """A widget to create a media player
    
    modified from example at https://pythonprogramminglanguage.com/pyqt5-video-widget/
    """

    def __init__(self, *args, **kwargs):
        """Constructor"""

        super().__init__(*args, **kwargs)

        self.mediaPlayer = QMediaPlayer(None, QMediaPlayer.VideoSurface)

        self.videoWidget = QVideoWidget()

        self.playButton = QToolButton()
        self.playButton.setEnabled(False)
        self.playButton.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.playButton.clicked.connect(self.play)

        self.positionSlider = QSlider(Qt.Horizontal)
        self.positionSlider.setRange(0, 0)
        self.positionSlider.sliderMoved.connect(self.setPosition)

        self.controlLayout = QHBoxLayout()
        self.controlLayout.setContentsMargins(0, 0, 0, 0)
        self.controlLayout.addWidget(self.playButton)
        self.controlLayout.addWidget(self.positionSlider)

        layout = QVBoxLayout()
        layout.addWidget(self.videoWidget)
        layout.addLayout(self.controlLayout)

        self.setLayout(layout)

        self.mediaPlayer.setVideoOutput(self.videoWidget)
        self.mediaPlayer.stateChanged.connect(self.mediaStateChanged)
        self.mediaPlayer.positionChanged.connect(self.positionChanged)
        self.mediaPlayer.durationChanged.connect(self.durationChanged)

    def openFile(self, path):
        """Opens the media file at the given path"""

        if path != '':
            self.mediaPlayer.setMedia(
                    QMediaContent(QUrl.fromLocalFile(path)))
            self.playButton.setEnabled(True)
        else: raise ValueError("Path can't be empty.")

    def play(self):
        """Plays/pauses the currently loaded video"""

        if self.mediaPlayer.state() == QMediaPlayer.PlayingState:
            self.mediaPlayer.pause()
        else:
            self.mediaPlayer.play()

    def mediaStateChanged(self, state):
        """Sets play/pause button depending on current video state"""

        if self.mediaPlayer.state() == QMediaPlayer.PlayingState:
            self.playButton.setIcon(
                    self.style().standardIcon(QStyle.SP_MediaPause))
        else:
            self.playButton.setIcon(
                    self.style().standardIcon(QStyle.SP_MediaPlay))

    def positionChanged(self, position):
        """Set slider for current position"""

        self.positionSlider.setValue(position)

    def durationChanged(self, duration):
        """Set slider for current position"""

        self.positionSlider.setRange(0, duration)

    def setPosition(self, position):
        """Set current position in video"""

        self.mediaPlayer.setPosition(position)

class Tag_Area(QWidget):
    """A widget to handle the tag area"""

    def __init__(self, main, *args, **kwargs):
        """Constructor
        
        Args:
            main = the main widget
        """

        super().__init__(*args, **kwargs)

        uic.loadUi(os.path.join(resource_path, "tag_area.ui"), self)

        self.main = main

        # setup tag area
        self.add_tag_btn.clicked.connect(self.add)
        self.chkboxs = []
        self.setup()

    def setup(self):
        """A method to setup the tag area with the current scraper's tags"""

        if self.main.scraper is None:
            self.setEnabled(False)
            return
        else:
            self.setEnabled(True)

        # create a new layout
        new_layout = QGridLayout()
        
        # row/column starting positions
        row = 0
        column = 0

        # get the size of one column unit (1/5th of the scroll area width)
        col_u = self.frameSize().width() / 5

        # set spacing to a known number
        new_layout.setHorizontalSpacing(10)

        for tg in self.chkboxs:
            tg.setParent(None)

        self.chkboxs = []
        # iterate through tags, adding them to layout
        for tag in self.main.scraper.tags:
            # make checkbox with correct status
            self.chkboxs.append(QCheckBox(tag))
            self.chkboxs[-1].setChecked(self.main.scraper.tags[tag])
            #self.chkboxs[-1].toggled.connect(lambda : print("yay bandaids?"))
            # figure out how many column units this tag should take up (factoring in spacing)
            col_span = max(1, math.ceil((self.chkboxs[-1].sizeHint().width()) / col_u))
            if col_span > 2:
                # check if with spacing, we fit in one fewer column
                if self.chkboxs[-1].sizeHint().width() <= ((col_span - 1) * col_u + (col_span - 2) * 10):
                    col_span -= 1
            # decide if column span should push this tag to a new row
            if col_span + column > 5 and column != 0:
                column = 0
                row += 1
            # add tag
            new_layout.addWidget(self.chkboxs[-1], row, column, 1, col_span)
            # calculate row/column start for next tag
            column = (min(column + col_span, 5)) % 5
            row = row + 1 if column == 0 else row

        # add add button
        new_layout.addWidget(self.add_tag_btn, row, column)

        # set old layout to temporary widget to re-parent it
        QWidget().setLayout(self.layout())

        # set new layout
        self.setLayout(new_layout) 

    def add(self):
        """A mthod to add a tag to the scraper's current tag list"""

        # make dialog to get relevant info
        dialog = QDialog()
        uic.loadUi(os.path.join(resource_path, "add_tag.ui"), dialog)
        
        # display dialog
        accepted = dialog.exec()

        # if dialog was accepted, add tag
        if accepted:
            try:
                # add tag to scraper
                self.main.scraper.add_tag(dialog.tag_nm.text(), dialog.tag_def_val.currentText() == "True")
                # redo tags in box
                self.setup()
            except Exception as e:
                warning = QMessageBox()
                warning.setText(str(e))
                warning.setIcon(QMessageBox.Warning)
                #warning.setTitle("Tag error")
                warning.exec()
        # otherwise, do nothing
        else: pass

class Main(QMainWindow):

    def __init__(self):
        """Constructor"""

        super().__init__()

        self.media_idx = 0
        self.unscaled_img = None

        # load in ui
        uic.loadUi(os.path.join(resource_path, "Main_window.ui"), self)

        # set window title
        self.setWindowTitle("Telegram tagger")

        # instantiate scraper
        self.scraper = None
        # instantiate google translate helper
        self.translator = translate.Client()

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

        # connect next and prev buttons for media
        self.prev_media_btn.clicked.connect(lambda _: self.load_media(self.media_idx-1))
        self.next_media_btn.clicked.connect(lambda _: self.load_media(self.media_idx+1))

        # connect next and prev buttons for message
        self.prev_msg_btn.clicked.connect(lambda _: (self.set_tags(), self.scraper.prev(), self.load_msg()))
        self.next_msg_btn.clicked.connect(lambda _: (self.set_tags(), self.scraper.next(), self.load_msg()))

        self.prev_msg_btn.setEnabled(False)
        self.next_msg_btn.setEnabled(False)

        # connect msg id field
        self.msg_id.setValidator(QIntValidator(bottom=0))
        self.msg_id.editingFinished.connect(self.jump_to_id)

        # connect comment field
        self.comment_box.textChanged.connect(self.parse_comment)

        # disable msg id box and comment box if necessary
        if self.scraper is None:
            self.msg_id.setEnabled(False)
            self.comment_box.setEnabled(False)
        else:
            self.msg_id.setEnabled(True)
            self.comment_box.setEnabled(True)

        self.tag_area = Tag_Area(self)
        self.tag_scroll_area.setWidget(self.tag_area)

        # if no session file (used for telegram authentication) is present,
        #   get one
        if not os.path.isfile(os.path.join(tel_scrape_path, "scraper.session")):
            num, accepted = QInputDialog.getText(self, "Tagger setup", "Phone number (with country code): ", QLineEdit.Normal, "")
            # if number wasn't submitted, exit
            if not accepted: sys.exit()

            # otherwise send request to phone number
            cf = ConfigParser()
            cf.read(os.path.join(tel_scrape_path, ".Telegram_info.ini"))
            
            client = TelegramClient("scraper", cf["Thesis"]["api_id"], cf["Thesis"]["api_hash"]) 
            client.connect()
            client.send_code_request(num)

            # get code from user
            code, accepted = QInputDialog.getText(self, "Tagger setup", "Enter code sent through Telegram: ", QLineEdit.Normal, "")
            # if number wasn't submitted, exit
            if not accepted: sys.exit()

            # authenticate
            client.sign_in(num, code)

            # now there should be a scraper.session file in the pwd
            if not os.path.isfile("scraper.session"): raise FileNotFoundError("No session file?")
            # move it to this program's directory
            os.rename("scraper.session", os.path.join(tel_scrape_path, "scraper.session"))

        # open settings window
        self.settings = Settings_window()
        # only need to show settings if we don't have already
        if not os.path.isfile(os.path.join(tel_scrape_path, "session.ini")):
            ret = self.settings.exec_()
            # if settings weren't confirmed, close
            if not ret: sys.exit()

            ok = False

            while not ok:
                # try to make scraper
                try:
                    self.make_scraper()
                    ok = True
                except AssertionError:
                    err = QMessageBox()
                    err.showMessage("\tDates invalid. Please be sure to check\nthat Start date is earlier than end date and that\nEnd date is at latest the current date.")
                    _ = err._exec()
                    # redisplay settings window  
                    ret = self.settings.exec_()
                    # if settings weren't confirmed, close
                    if not ret: sys.exit()
        # otherwise create a scraper
        else:
            ok = False

            while not ok:
                # try to make scraper
                try:
                    self.make_scraper()
                    ok = True
                except AssertionError:
                    err = QMessageBox()
                    err.showMessage("\tDates invalid. Please be sure to check\nthat Start date is earlier than end date and that\nEnd date is at latest the current date.")
                    _ = err._exec()
                    # redisplay settings window  
                    ret = self.settings.exec_()
                    # if settings weren't confirmed, close
                    if not ret: sys.exit()

        # setup menu bar
        taggermenu = self.menuBar().addMenu("Tagger")

        settings_act = QAction(QIcon(":icons/settings"), "Settings", self)
        settings_act.triggered.connect(self.open_settings)
        taggermenu.addAction(settings_act)

        self.filter = Filter_window(main_window = self)

        filter_act = QAction(QIcon(":icons/filter"), "Filters", self)
        filter_act.triggered.connect(self.open_filter)
        taggermenu.addAction(filter_act)

        # show GUI
        self.show()

        # set channel info if session file exists
        if os.path.isfile(os.path.join(tel_scrape_path, "session.ini")):
            cf = ConfigParser()
            cf.read(os.path.join(tel_scrape_path, "session.ini"))

            # set id
            self.scraper.get_msg_by_id(int(cf["Scraper"]["msg_id"]))
            # load message
            self.load_msg()
            # load media
            try: self.load_media(self.scraper.media.index(int(cf["Scraper"]["media_id"])))
            except: pass
        else:
            # placeholder is tiny for some reason at start so we load
            #   media after showing window to scale correctly
            self.load_media(0)

    def open_filter(self):
        """Method to open the window to change filters"""

        self.filter.exec_()

    def open_settings(self):
        """Open the settings window and change the scraper if necessary"""

        ret = self.settings.exec_()
        # if settings weren't confirmed, close
        if not ret: sys.exit()

        ok = False

        while not ok:
            # try to make scraper
            try:
                self.make_scraper()
                ok = True
            except AssertionError:
                err = QMessageBox()
                err.showMessage("\tDates invalid. Please be sure to check\nthat Start date is earlier than end date and that\nEnd date is at latest the current date.")
                _ = err._exec()
                # redisplay settings window  
                ret = self.settings.exec_()
                # if settings weren't confirmed, close
                if not ret: sys.exit()

    def parse_comment(self):
        """Limits the comment box to 255 characters"""

        # if text is too long, truncate it
        if len(self.comment_box.toPlainText()) > 255:
            # otherwise, truncate to 255 characters
            self.comment_box.setPlainText(self.comment_box.toPlainText()[:255])
            # put cursor at end of text
            curs = self.comment_box.textCursor()
            curs.setPosition(255)
            self.comment_box.setTextCursor(curs)

        # update message's comment field (which will be committed 
        #   when message is changed or when scraper is cleaned up)
        if not self.scraper is None:
            self.scraper.comment = self.comment_box.toPlainText()

    def jump_to_id(self, id=None):
        """Jumps to the given id, or to the id in the msg_id box if id is None

        Args:
            id = the id to jump to, or use msg_id line edit if None
        """

        if id is None:
            id = int(self.msg_id.text())

        if id < 0: raise ValueError("ID must be positive")

        if self.scraper is None: raise AttributeError("No active scraper.")

        try:
            self.set_tags()
            self.scraper.get_msg_by_id(id, False)
            self.load_msg()
            self.msg_id.setStyleSheet("")
            self.msg_id.setToolTip("")
        except EndRange:
            self.msg_id.setText(str(self.scraper.msg_id))
            self.msg_id.setStyleSheet("background-color:red;")
            self.msg_id.setToolTip("ID {} not in date range.".format(id)) 
        except XPostThrowaway as e:
            self.msg_id.setText(str(self.scraper.msg_id))
            self.msg_id.setStyleSheet("background-color:red;")
            self.msg_id.setToolTip("ID {} is {}.".format(id, str(e).lower())) 

    def make_scraper(self):
        """Make a scraper"""
        
        # convert dates to datetimes in utc
        start = self.settings.date_from.dateTime()
        start = datetime(year = start.date().year(), month = start.date().month(), day = start.date().day(),
            hour = start.time().hour(), minute = start.time().minute(), second = start.time().second(),
            tzinfo=timezone.utc) + timedelta(hours = utcoffset)
        end = self.settings.date_to.dateTime()
        end = datetime(year = end.date().year(), month=end.date().month(), day=end.date().day(),
            hour = end.time().hour(), minute = end.time().minute(), second = end.time().second(),
            tzinfo=timezone.utc) + timedelta(hours = utcoffset)
        # validate dates
        assert end <= datetime.now().astimezone(timezone.utc)
        assert start <= end

        # if this describes the current scraper, do nothing
        if self.scraper is not None:
            if self.scraper.start == start and self.scraper.end == end:
                if self.scraper.chnl.username == self.settings.chnl.text().split("/")[-1]: return

        # try to make scraper
        try: 
            # cleanup old scraper
            if self.scraper is not None: 
                self.set_tags()
                self.scraper._cleanup()
                self.scraper = None
            self.scraper = Scraper(chnl = self.settings.chnl.text(), start = start, end = end,
                db = self.settings.db_path.text(), x_post_excl = self.settings.excludes,
                dwnld_media = self.settings.media_sv.isChecked())
            self.orig_msg.setToolTip("")
            self.orig_msg.setStyleSheet("")
        except ValueError:
            self.orig_msg.setStyleSheet("background-color:red;")
            self.orig_msg.setToolTip("No messages for this channel in\nthe given date range.")
            self.orig_msg.setText("")
        except Exception as e:
            self.orig_msg.setStyleSheet("background-color:red;")
            self.orig_msg.setToolTip("No messages for this channel in\nthe given date range.") 
        finally:
            if self.scraper is None:
                self.msg_id.setEnabled(False)
                self.comment_box.setEnabled(False)
            else:
                self.msg_id.setEnabled(True)
                self.comment_box.setEnabled(True)

        self.load_msg()

    def set_tags(self):
        """Pulls tags from tag area and loads them into scraper"""

        for bx in self.tag_area.findChildren(QCheckBox):
            self.scraper.tags[bx.text()] = bx.isChecked()

    def load_msg(self):
        """Loads the message currently held by
            the scraper"""

        # load tags
        self.tag_area.setup()

        # clear messages if there's no valid scraper
        if self.scraper is None:
            self.orig_msg.setText("No messages for this channel in that date range")
            self.trans_msg.setText("No messages for this channel in that date range")
            self.msg_id.setText("")
            self.prev_msg_btn.setEnabled(False)
            self.next_msg_btn.setEnabled(False)
            self.date.setText("---")
            self.xpost.setText("---")
            self.reply.setText("---")
            return

        # otherwise set original text to message text
        self.orig_msg.setText(self.scraper.msg)

        # and try to translate
        try:
            trans = self.translator.translate(self.scraper.msg, target_language='en', format_="text")
            self.trans_msg.setText(trans["translatedText"])
        except Exception:
            self.trans_msg.setText("Error occurred with translation. Check internet connection.")

        # set message id box
        self.msg_id.setText("{}".format(self.scraper.msg_id))

        self.unscaled_img = None

        # disable next/prev message and media buttons if necessary
        try:
            self.scraper.prev()
            self.scraper.next()
            self.prev_msg_btn.setEnabled(True)
        except EndRange:
            self.prev_msg_btn.setEnabled(False)

        try:
            self.scraper.next()
            self.scraper.prev()
            self.next_msg_btn.setEnabled(True)
        except EndRange:
            self.next_msg_btn.setEnabled(False)

        # reset style sheet to get rid of any errors previously indicated
        self.msg_id.setStyleSheet("")
        self.msg_id.setToolTip("")

        # set date
        self.date.setText(f"{self.scraper.msg_dat:%B %d, %Y}")

        # set xpost if this is a crosspost
        self.xpost.setText(self.scraper.fwd if (self.scraper.fwd is not None and len(self.scraper.fwd) > 0) else "---")

        # set reply link if this is a crosspost
        self.reply.setText(f'<a href="t.me/{self.scraper.reply_channel}/{self.scraper.reply_msg_id}>{self.scraper.reply_channel}</a>' if self.scraper.reply_channel is not None else "---")

        # load comment field
        try: self.comment_box.setPlainText(self.scraper.comment)
        except: self.comment_box.setPlainText("")

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

        try:
            if self.unscaled_img is None or self.media_idx != idx:
                try:
                    self.media_f = self.scraper.get_media(self.scraper.media[idx%len(self.scraper.media)]) 
                except (IndexError, AttributeError, ZeroDivisionError):
                    self.media_f = ":/placeholder/no_img.jpg"

                if self.media_f.endswith((".jpg", ".png", ".gif")):
                    # if previous media was movie, make sure it's paused
                    try:
                        if self.media_type == "movie":
                            if self.media_box.currentWidget().mediaPlayer.state() == QMediaPlayer.PlayingState: 
                                self.media_box.currentWidget().mediaPlayer.pause()
                    except: pass
                    self.media_type = "label"
                    # set media box to qlabel widget
                    self.media_box.setCurrentIndex(0)
                    # make a QMovie to get unscaled frame
                    _ = QMovie(self.media_f)
                    _.jumpToFrame(0)
                    self.unscaled_img = _.currentImage()
                else:
                    self.media_type = "movie"
                    self.media_box.setCurrentIndex(1)
                    try:
                        self.media_box.currentWidget().openFile(self.media_f)
                    # if there was an error, display placeholder image
                    except Exception:
                        self.media_f = ":/placeholder/no_img.jpg"
                        self.media_type = "label"
                        # set media box to qlabel widget
                        self.media_box.setCurrentIndex(0)
                        # make a QMovie to get unscaled frame
                        _ = QMovie(self.media_f)
                        _.jumpToFrame(0)
                        self.unscaled_img = _.currentImage()

            # video player will resize and scale itself correctly so we only have
            #   to worry about size if in "label" mode
            if self.media_type == "label":
                # get label
                label = self.media_box.currentWidget().layout().itemAt(0).widget()
                # get aspect ratio
                scaled_size = self.unscaled_img.scaled(label.width(),
                            label.height(), Qt.KeepAspectRatio).size()

                # load new movie (scaling doesn't work once we jump to frame)
                movie = QMovie(self.media_f)
                # scale down
                movie.setScaledSize(scaled_size)
                label.setMovie(movie)
                movie.start()
                # set minimum size so we can scale back down
                label.setMinimumSize(QSize(1,1))
            
            self.media_idx = idx

            # disable buttons
            if self.scraper is None or len(self.scraper.media) <= 1:
                self.prev_media_btn.setEnabled(False)
                self.next_media_btn.setEnabled(False)
            else:
                self.prev_media_btn.setEnabled(True)
                self.next_media_btn.setEnabled(True)

            # set media id
            try:
                self.media_id.setText("{}".format(self.scraper.media[idx%len(self.scraper.media)]))
            except:
                self.media_id.setText("---")
        except: pass

    def resizeEvent(self, *args, **kwargs):
        """Implement resize event so we can reload image when window is made bigger"""

        super().resizeEvent(*args, **kwargs)

        self.load_media(self.media_idx)

    def closeEvent(self, e):
        """Catch close"""

        try: self.set_tags()
        except: pass

        try: self.scraper._cleanup()
        except: pass

        try:
            cf = ConfigParser()
            # store settings info
            cf["Settings"] = {"db_loc":self.settings.db_path.text(),
                              "excludes":"|".join(self.settings.excludes),
                              "sv_media":self.settings.media_sv.isChecked()}
            # store info about current scraper if there is one
            if self.scraper is not None:
                cf["Scraper"] = {"start":self.scraper.start - timedelta(hours = utcoffset),
                                 "end":self.scraper.end - timedelta(hours = utcoffset),
                                 "chnl":self.scraper.chnl.username,
                                 "msg_id":self.scraper.msg_id,
                                 "media_id":self.media_id.text()}

            # write config file
            with open(os.path.join(tel_scrape_path, "session.ini"), "w") as f:
                cf.write(f)
        except Exception as exc: print(exc)

        super().closeEvent(e)

if __name__ == "__main__":

    app = QApplication(sys.argv)
    QCoreApplication.setAttribute(Qt.AA_DontUseNativeMenuBar)
    widge = Main()
    sys.exit(app.exec_())