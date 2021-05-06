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