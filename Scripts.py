from Scraper import Scraper
from datetime import datetime, timedelta, timezone
from configparser import ConfigParser
import os, sys
import sqlite3
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter

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

    # get what days posts were on
    set_1_days = [post[4][:10] for post in set_1]
    set_2_days = [post[4][:10] for post in set_2]

    # get days for all the messages pulled
    start = datetime(year = 2020, month = 8, day = 1)
    end = datetime(year = 2020, month = 12, day = 1)
    days = [start]
    while days[-1] + timedelta(days = 1) < end:
        days.append(days[-1] + timedelta(days = 1))

    # get number of posts per day
    set_1_cnts = [set_1_days.count(date.isoformat()[:10]) for date in days]
    set_2_cnts = [set_2_days.count(date.isoformat()[:10]) for date in days]

    # make subfigure to have more control over axes
    fig, ax = plt.subplots()

    # add title
    plt.title("Posts referencing the elderly compared to posts referencing WWII")
    # plot data
    plt.plot(days, set_1_cnts, label = "Elderly")
    plt.plot(days, set_2_cnts, label = "WWII")

    # format dates
    ax.xaxis.set_major_formatter(DateFormatter("%m-%d"))

    # add axis labels
    plt.ylabel("Counts of posts per day")
    plt.xlabel("Date (UTC)")

    # add legend
    plt.legend()

    # plot figure
    plt.show()

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