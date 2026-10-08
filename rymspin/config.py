"""Settings shared by the modules: RYM's address, the data folder and the defaults."""

import os
from pathlib import Path

BASE = "https://rateyourmusic.com"


PER_PAGE = 25


DATA_DIR = Path(os.environ.get("RYMSPIN_HOME") or Path.home() / ".rymspin")


MAX_PAGES = 5  # pages loaded from RYM at most per run when filters skip releases


RELEASE_TYPES = [
    "album",
    "ep",
    "single",
    "comp",
    "mixtape",
    "djmix",
    "musicvideo",
    "video",
    "additional",
    "bootleg",
    "unauth",
]
