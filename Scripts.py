from Scraper import Scraper
from datetime import datetime, timedelta, timezone
from configparser import ConfigParser
import os

working_dir = os.path.join(os.path.expanduser("~"), "Documents", "Thesis")

# get api info
cf = ConfigParser()
_ = cf.read(os.path.join(working_dir, ".Telegram_info.ini"))
if len(_) == 0:
    raise FileNotFoundError("No telegram info file found.")

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
        sys.stdout.write(u"\u001b[2K")
        sys.stdout.write("\rFetching message {}".format(scraper.msg_id))
        sys.stdout.flush()
        for media_id in scraper.media:
            sys.stdout.write(u"\u001b[2K")
            sys.stdout.write("\rFetching message {}  --  media for message {}".format(media_id, scraper.msg_id))
            sys.stdout.flush()
            scraper.get_media(media_id)
    
    sys.stdout.write(u"\u001b[2K")
    sys.stdout.write("\rDone.\n")
    sys.stdout.flush()