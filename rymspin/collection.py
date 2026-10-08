"""Pages of a RYM collection, saved to disk so repeated runs don't load them again."""

import hashlib
import json
import time

from . import parsing
from .config import DATA_DIR

CACHE_DIR = DATA_DIR / "cache"

CACHE_TTL = 6 * 3600  # seconds a saved page is reused


OWN_COLLECTION_TTL = 7 * 24 * 3600  # for --new-from, which reads the user's whole collection


CACHE_VERSION = 2  # change when parse_rows() returns different fields


class Collection:
    """Pages of a collection URL, saved to disk for CACHE_TTL seconds."""

    def __init__(self, fetcher, url, refresh=False, ttl=CACHE_TTL):
        self.fetcher = fetcher
        self.url = url
        self.refresh = refresh
        self.ttl = ttl
        self._pages = {}

    def page(self, number):
        """Return (rows, last page number), or None if the collection doesn't exist."""
        if number not in self._pages:
            self._pages[number] = self._saved(number) or self._load(number)
        return self._pages[number]

    def is_available(self, number):
        """Whether the page can be returned without loading it from RYM."""
        if number not in self._pages:
            saved = self._saved(number)
            if saved is None:
                return False
            self._pages[number] = saved
        return True

    def _url(self, number):
        return self.url if number == 1 else f"{self.url.rstrip('/')}/{number}"

    def _path(self, number):
        key = f"{CACHE_VERSION} {self._url(number)}"
        return CACHE_DIR / (hashlib.sha1(key.encode()).hexdigest() + ".json")

    def _saved(self, number):
        if self.refresh:
            return None
        try:
            saved = json.loads(self._path(number).read_text())
            if time.time() - saved["time"] < self.ttl:
                return saved["rows"], saved["pages"]
        except (OSError, ValueError, KeyError):
            pass
        return None

    def _load(self, number):
        url, path = self._url(number), self._path(number)
        soup = self.fetcher.get(url)
        if soup.find("table", class_="mbgen") is None:
            return None
        rows, pages = parsing.parse_rows(soup), parsing.last_page(soup)
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"time": time.time(), "url": url, "rows": rows, "pages": pages}))
        except OSError:
            pass
        return rows, pages
