from Scraper import Scraper
from datetime import datetime, timedelta, timezone
from configparser import ConfigParser
import os, sys
import sqlite3
import numpy as np

working_dir = os.path.join(os.path.expanduser("~"), "Documents", "Thesis")

# get api info
cf = ConfigParser()
_ = cf.read(os.path.join(working_dir, ".Telegram_info.ini"))
if len(_) == 0:
    raise FileNotFoundError("No telegram info file found.")

def avg_win(chnl, start_id, end_id, type_):
    """Return mean, median, and std of views in id range for channel

    Args:
        chnl = the channel to look at
        start_id = id to start range (inclusive)
        end_id = the id to end range (inclusive)
        type = one of "views" or "forwards"
    Returns:
        float, float, float = mean, standard deviation, median
    """

    if not type_.lower() in ["views", "forwards"]:
        raise ValueError("type_ must be either views or forwards, not {}".format(type_))

    with sqlite3.connect("/Users/gretathesis/Desktop/Thesis.db") as db:
        msgs = db.execute("SELECT `{}` FROM Scraper WHERE `CHANNEL` = ? AND `ID` BETWEEN ? AND ?".format(type_), (chnl, start_id, end_id)).fetchall()

    if len(msgs) == 0:
        raise ValueError("No info found for channel {} between id {} and id {}".format(chnl, start_id, end_id))

    nums = np.array([msg[0] for msg in msgs])
    mean = np.mean(nums, 0)
    std = np.std(nums, 0)
    med = np.median(nums, 0)
    print("{} for range: {}".format(type_, nums))
    print("mean: {}, std: {}, median: {}".format(mean, std, med))
    return mean, std, med

def download_chnl(chnl, start, end, db=os.path.join(working_dir, "Thesis.db"), verbose=True):
    """Download all messages and media to the given database for the given channel
        in the given date ranges

    Args:
        chnl    = the username of the channel (t.me/...)
        start   = a utc datetime for the start of the range
        end     = a utc datetime fo rthe end of the range
        db      = the database to store information in 
        verbose = whether to print update information
    """

    scraper = Scraper(chnl=chnl, start=start, end=end, db=db, dwnld_media=True)

    for msg in scraper:
        if verbose:
            sys.stdout.write(u"\u001b[2J")
            sys.stdout.write("\rFetching message {}".format(scraper.msg_id))
            sys.stdout.flush()
        for media_id in scraper.media:
            if verbose:
                sys.stdout.write(u"\u001b[2J")
                sys.stdout.write("\rFetching message {}  --  media for message {}".format(media_id, scraper.msg_id))
                sys.stdout.flush()
            scraper.get_media(media_id)

    if verbose:
        sys.stdout.write(u"\u001b[2J")
        sys.stdout.write("\rDone.\n")
        sys.stdout.flush()