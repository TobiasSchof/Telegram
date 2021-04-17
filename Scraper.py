from astropy.io import fits
from telethon import TelegramClient
from datetime import datetime
from configparser import ConfigParser
import telethon.sync # this relieves the need to use telethon as an asyncio library

def load_range(channel:str, start:datetime, end:datetime, data_dir:str, download_media:bool=False):
    """loads and files 