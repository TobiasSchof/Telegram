#!/usr/bin/env python

# inherent python libraries
from datetime import datetime, timezone, timedelta
from glob import glob
import sys, os

# installs
from PyQt5.QtWidgets import (QApplication, QMainWindow, QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
    QGroupBox, QLabel, QFileDialog, QToolButton, QLineEdit, QStyle, QSlider)
from PyQt5.QtCore import Qt, QDateTime, QTimeZone, QSize, QUrl
from PyQt5.QtGui import QMovie, QIntValidator
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5 import uic
from googletrans import Translator

# project files
sys.path.append(os.path.normpath(os.path.abspath(__file__) + (os.sep + os.pardir) * 2))
from Scraper import Scraper, EndRange, NoMedia
import resources.images

# utc offset to get from QDateTimeEdit to UTC
#   (E.g. Belarus is UTC+3 so utcoffset of -3 is used here)
utcoffset = -3

# get path to resources folder
resource_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")

# Telegram Scraper folder
tel_scrape_path = os.path.join(os.path.expanduser("~"), "Telegram Scraper")

if not os.path.isdir(tel_scrape_path):
    os.mkdir(tel_scrape_path)

class Settings_window(QDialog):
    """A widget to hold information about the scraper's settings"""

    def __init__(self, *args, **kwargs):
        """Constructor"""

        super().__init__(*args, **kwargs)

        # load ui
        uic.loadUi(os.path.join(resource_path, "Settings_window.ui"), self)

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
        self.db_edit.pressed.connect(self.edit_db_loc)

        # check if there are any databases in default location
        dbs = glob(os.path.join(tel_scrape_path, "*.db"))
        if len(dbs) > 0: self.db_path.setText(dbs[0])
        else: self.db_path.setText(os.path.join(tel_scrape_path, "Project1.db"))

        # TODO: Fetch previous settings from .ini file

    def parse(self):
        """A method to parse all the cross post items"""

        self.excludes = [""]
        removes = []
        for idx in range(0, self.x_post_layout.count()):
            # get widget
            widge = self.x_post_layout.itemAt(idx).widget()
            # if we find a blank channel, add it to the list of widgets to remove
            if widge.chnl_nm.text() == "": removes.insert(0, idx)
            # otherwise add it to the list of channels to exclude
            else: self.excludes.insert(1, widge.chnl_nm.text())

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
            widge.dlt_btn.pressed.connect(rmv)
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
            w.dlt_btn.pressed.disconnect()
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
        self.date_from.dateTimeChanged.connect(self.edit_scraper)
        self.date_to.dateTimeChanged.connect(self.edit_scraper)

        # connect next and prev buttons for media
        self.prev_media_btn.clicked.connect(lambda _: self.load_media(self.media_idx-1))
        self.next_media_btn.clicked.connect(lambda _: self.load_media(self.media_idx+1))

        # connect next and prev buttons for message
        self.prev_msg_btn.clicked.connect(lambda _: (self.scraper.prev(), self.load_msg()))
        self.next_msg_btn.clicked.connect(lambda _: (self.scraper.next(), self.load_msg()))

        self.prev_msg_btn.setEnabled(False)
        self.next_msg_btn.setEnabled(False)

        # connect channel id setting
        self.msg_id.setValidator(QIntValidator(bottom=0))
        self.msg_id.editingFinished.connect(self.jump_to_id)

        # setup the movie player 

        # open settings window
        self.settings = Settings_window()
        ret = self.settings.exec_()
        # if settings weren't confirmed, close
        if not ret: sys.exit()

        # show GUI
        self.show()

        # placeholder is tiny for some reason at start so we load
        #   media after showing window to scale correctly
        self.load_media(0)

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
            self.scraper.get_msg_by_id(id, False)
            self.load_msg()
            self.msg_id.setStyleSheet("")
            self.msg_id.setToolTip("")
        except EndRange:
            self.msg_id.setText(str(self.scraper.msg_id))
            self.msg_id.setStyleSheet("background-color:red;")
            self.msg_id.setToolTip("ID {} not in date range.".format(id)) 

    def edit_scraper(self):
        """Change the channel being parsed"""
        
        # convert dates to datetimes in utc
        start = self.date_from.dateTime()
        start = datetime(year = start.date().year(), month = start.date().month(), day = start.date().day(),
            hour = start.time().hour(), minute = start.time().minute(), second = start.time().second(),
            tzinfo=timezone.utc) + timedelta(hours = utcoffset)
        end = self.date_to.dateTime()
        end = datetime(year = end.date().year(), month=end.date().month(), day=end.date().day(),
            hour = end.time().hour(), minute = end.time().minute(), second = end.time().second(),
            tzinfo=timezone.utc) + timedelta(hours = utcoffset)
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
                if self.scraper.chnl.username == self.chnl.text().split("/")[-1]: return

        # try to make scraper
        try: 
            # cleanup old scraper
            if self.scraper is not None: 
                self.scraper._cleanup()
                self.scraper = None
            self.scraper = Scraper(chnl = self.chnl.text(), start = start, end = end,
                db = self.settings.db_path.text(), dwnld_media = self.settings.media_sv.isChecked())
            self.chnl.setToolTip("The telegram channel to parse.")
            self.chnl.setStyleSheet("")
        except ValueError:
            self.chnl.setStyleSheet("background-color:red;")
            self.chnl.setToolTip("No messages for this channel in\nthe given date range.")
            self.chnl.setText("")
        except Exception as e:
            print(e)
            self.chnl.setStyleSheet("background-color:red;")
            self.chnl.setToolTip("No messages for this channel in\nthe given date range.") 

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
        self.orig_msg.setText(self.scraper.msg)

        # and try to translate
        try:
            trans = self.translator.translate(self.scraper.msg, src="ru")
            self.trans_msg.setText(trans.text)
        except Exception as e:
            print(e)
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
                    except Exception as e:
                        print(e)
                        self.media_f = ":/placeholder/no_img.jpg"
                        self.media_type = "label"
                        # set media box to qlabel widget
                        self.media_box.setCurrentIndex(0)
                        # make a QMovie to get unscaled frame
                        _ = QMovie(self.media_f)
                        _.jumpToFrame(0)
                        self.unscaled_img = _.currentImage()

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
        except Exception as e: raise e

    def resizeEvent(self, *args, **kwargs):
        """Implement resize event so we can reload image when window is made bigger"""

        super().resizeEvent(*args, **kwargs)

        self.load_media(self.media_idx)

if __name__ == "__main__":

    app = QApplication(sys.argv)
    widge = Main()
    sys.exit(app.exec_())