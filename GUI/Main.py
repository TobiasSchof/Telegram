#!/usr/bin/env python

# inherent python libraries
import sys, os

# installs
from PyQt5.QtWidgets import QApplication, QMainWindow, QAction
from PyQt5 import uic

# get path to resources folder
resource_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")

# Telegram Scraper folder
tel_scrape_path = os.path.join(os.path.expanduser("~"), "Telegram Scraper")

if not os.path.isdir(tel_scrape_path):
    print(tel_scrape_path)
    #os.mkdir(tel_scrape_path)

class Main(QMainWindow):

    def __init__(self):
        """Constructor"""

        super().__init__()

        # load in ui
        uic.loadUi(os.path.join(resource_path, "Main_window.ui"), self)

        # set window title
        self.setWindowTitle("Telegram tagger")

        # show GUI
        self.show()

if __name__ == "__main__":

    app = QApplication(sys.argv)
    widge = Main()
    sys.exit(app.exec_())