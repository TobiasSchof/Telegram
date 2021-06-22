Telegram

This project is to create a tool to collect Telegrams from a collection of Telegram channels during a timeperiod and providing them in an interface that makes it   easy to tag them. Files are stored as fits files.

Dependencies:
  Telethon (For python Telegram API)
  PyQt5    (For GUI)
  googletrans alpha [pip install googletrans==3.1.0a0] (For translations)

SQLite database:

Table "Scraper" will contain the following fields:
(see https://core.telegram.org/constructor/message for a description of fields)

0  Channel  TINYTEXT
1  ID       INT UNSIGNED
2  Media    TINYTEXT         = comma separated list of the ids of any media attached to this message
3  Xpost    TINYTEXT         = the channel name for the channel from which this post was crossposed from (if any)
4  DT       DATETIME         = in utc
5  Message  MEDIUMTEXT
6  Silent   BOOL
7  Legacy   BOOL
8  Edt_hid  BOOL             = edit_hide
9  Pinned   BOOL
10 Bot_id   INT UNSIGNED
11 Reply_to TINYTEXT         = comma separated list channel name, msg_id
12 Views    INT UNSIGNED
13 Forwards INT UNSIGNED
14 Replies  INT UNSIGNED
15 edt_dt   DATETIME         = edit_dat in utc
16 Comment  TINYTEXT
                

Additionally, <tagname> BOOL columns (NULLable, default value False) will be added per tag 