from Scraper import Scraper
from datetime import datetime, timedelta, timezone
from configparser import ConfigParser
import os, sys
import sqlite3
import numpy as np
import matplotlib.pyplot as plt

working_dir = os.path.join(os.path.expanduser("~"), "Documents", "Thesis")

# get api info
cf = ConfigParser()
_ = cf.read(os.path.join(working_dir, ".Telegram_info.ini"))
if len(_) == 0:
    raise FileNotFoundError("No telegram info file found.")

def plot():
    """A function to plot things from the database"""

    # make this point to the database you want
    with sqlite3.connect("/Users/gretathesis/Desktop/Thesis.db") as db:
        # fill in what tags, etc you want to graph here
        set_1 = db.execute("SELECT * FROM Scraper WHERE (`CHANNEL` = 'nexta_tv' OR `CHANNEL` = 'nexta_live') AND NOT (`XPost` = 't.me/nexta_tv' OR `XPost` = 't.me/nexta_live' OR `XPost` = 't.me/luxta_tv') AND (`1.3 Elderly` = 1 OR `3.3.1 Traditional Base` = 1)").fetchall()
        set_2 = db.execute("SELECT * FROM Scraper WHERE (`CHANNEL` = 'nexta_tv' OR `CHANNEL` = 'nexta_live') AND NOT (`XPost` = 't.me/nexta_tv' OR `XPost` = 't.me/nexta_live' OR `XPost` = 't.me/luxta_tv') AND (`13. WWII` = 1)").fetchall()

    # get days for all the messages pulled
    set_1_days = [post[4][:10] for post in set_1]
    set_2_days = [post[4][:10] for post in set_2]

    # get unique days
    set_1_days_u = []
    for date in set_1_days:
        if date not in set_1_days_u: set_1_days_u.append(date)
    set_2_days_u = []
    for date in set_2_days:
        if date not in set_2_days_u: set_2_days_u.append(date)

    # sort days
    set_1_days_u.sort()
    set_2_days_u.sort()

    # get number of posts per day
    set_1_cnts = [set_1_days.count(date) for date in set_1_days_u]
    set_2_cnts = [set_2_days.count(date) for date in set_2_days_u]

    # get figure, axis so we can modify appearance
    fig, ax = plt.subplots()

    # plot data
    ax.plot(set_1_days_u, set_1_cnts)
    ax.plot(set_2_days_u, set_2_cnts)

    # get x tick labels (every 14 days)
    start = datetime(year = 2020, month = 8, day = 1)
    end = datetime(year = 2020, month = 12, day = 1)
    ticks = [start]
    while ticks[-1] + timedelta(days = 14) < end:
        ticks.append(ticks[-1] + timedelta(days = 14))

    # change ticks to YYYY-MM-DD
    ticks = [date.isoformat()[:10] for date in ticks]
    ax.set_xticks(ticks)

    # plot figure
    fig.show()
    plt.show(block=False)

    return fig, ax

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