#!/usr/bin/env python3
"""Pick a random release from the ones a Rate Your Music user has rated.

Usage:
    python rym_random.py USER [--min 0.5] [--max 5.0] [--show]

RYM is behind Cloudflare, so a real Chrome controlled with Playwright is used.
The profile is stored in ~/.rym-random/profile/ (or $RYM_RANDOM_HOME) to reuse the Cloudflare cookie between
runs. The browser runs without a window; one only opens if Cloudflare asks for
a verification (or with --show).
"""

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = "https://rateyourmusic.com"
PER_PAGE = 25
DATA_DIR = Path(os.environ.get("RYM_RANDOM_HOME") or Path.home() / ".rym-random")
PROFILE_DIR = DATA_DIR / "profile"
CACHE_DIR = DATA_DIR / "cache"
CACHE_TTL = 6 * 3600  # seconds a saved page is reused


class Fetcher:
    """Chrome browser with a persistent profile.

    Starts headless; if Cloudflare doesn't let it through, it reopens with a
    visible window so the challenge can be solved by hand. Chrome is only
    launched on the first request, so runs served from the cache don't open it.
    """

    def __init__(self, headless=True):
        self.headless = headless
        self._pw = None
        self._ctx = None

    def _launch(self, headless):
        if self._ctx is not None:
            self._ctx.close()
        self.headless = headless
        opts = dict(
            channel="chrome",
            headless=headless,
            ignore_default_args=["--enable-automation"],
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._ctx = self._pw.chromium.launch_persistent_context(PROFILE_DIR, **opts)
        if headless:
            # The headless user agent contains "HeadlessChrome", which Cloudflare
            # detects and which invalidates the cookie obtained with a window.
            ua = self._new_page().evaluate("navigator.userAgent")
            if "HeadlessChrome" in ua:
                self._ctx.close()
                opts["user_agent"] = ua.replace("HeadlessChrome", "Chrome")
                self._ctx = self._pw.chromium.launch_persistent_context(PROFILE_DIR, **opts)
        self._page = self._new_page()

    def _new_page(self):
        return self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def get(self, url):
        if self._pw is None:
            self._pw = sync_playwright().start()
            self._launch(self.headless)
        self._page.goto(url)
        # Wait for the Cloudflare challenge to clear. Headless waits briefly
        # and, if it doesn't pass, retries with a window (up to ~60 s, in case
        # the checkbox has to be ticked by hand).
        for _ in range(10 if self.headless else 60):
            if "Just a moment" not in self._page.title():
                break
            self._page.wait_for_timeout(1000)
        else:
            if self.headless:
                print("Cloudflare asks for a verification; opening a window...", file=sys.stderr)
                self._launch(headless=False)
                return self.get(url)
            sys.exit("Couldn't get past the Cloudflare protection.")
        self._page.wait_for_load_state("networkidle")
        return BeautifulSoup(self._page.content(), "html.parser")

    def close(self):
        if self._ctx is not None:
            self._ctx.close()
        if self._pw is not None:
            self._pw.stop()


class Collection:
    """Pages of a collection URL, saved to disk for CACHE_TTL seconds."""

    def __init__(self, fetcher, url, refresh=False):
        self.fetcher = fetcher
        self.url = url
        self.refresh = refresh
        self._pages = {}

    def page(self, number):
        """Return (rows, last page number), or None if the collection doesn't exist."""
        if number not in self._pages:
            self._pages[number] = self._load(number)
        return self._pages[number]

    def _load(self, number):
        url = self.url if number == 1 else f"{self.url}/{number}"
        path = CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".json")
        if not self.refresh:
            try:
                saved = json.loads(path.read_text())
                if time.time() - saved["time"] < CACHE_TTL:
                    return saved["rows"], saved["pages"]
            except (OSError, ValueError, KeyError):
                pass
        soup = self.fetcher.get(url)
        if soup.find("table", class_="mbgen") is None:
            return None
        rows, pages = parse_rows(soup), last_page(soup)
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"time": time.time(), "url": url, "rows": rows, "pages": pages}))
        except OSError:
            pass
        return rows, pages


def parse_rows(soup):
    table = soup.find("table", class_="mbgen")
    if table is None:
        return []
    albums = []
    for row in table.find_all("tr", id=re.compile(r"^page_catalog_item_\d+")):
        artists = row.select("a.artist")
        album = row.select_one("a.album")
        if album is None:
            continue
        rating = row.select_one("td.or_q_rating_date_s img")
        year = row.select_one("div.or_q_albumartist span.smallgray")
        albums.append({
            "artist": " & ".join(a.get_text(" ", strip=True) for a in artists) or "?",
            "title": album.get_text(" ", strip=True),
            "year": year.get_text(strip=True).strip("()") if year else "",
            "rating": rating["title"].replace(" stars", "") if rating else "?",
            "url": BASE + album["href"],
        })
    return albums


def last_page(soup):
    nums = [int(a.get_text()) for a in soup.select("a.navlinknum") if a.get_text().isdigit()]
    return max(nums, default=1)


def random_release(collection):
    """Pick a release uniformly at random from the collection.

    Picks a random page and position; if the position doesn't exist (only
    possible on the last page, which is incomplete), it picks again. Only the
    pages that are picked get loaded.
    """
    pages = collection.page(1)[1]
    while True:
        page = collection.page(random.randint(1, pages))
        rows = page[0] if page else []
        slot = random.randrange(PER_PAGE)
        if slot < len(rows):
            return rows[slot]


def rating(value):
    """argparse type for a RYM rating: 0.5 to 5.0 in steps of 0.5."""
    try:
        r = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a number")
    if not 0.5 <= r <= 5.0 or r * 2 != int(r * 2):
        raise argparse.ArgumentTypeError(f"{value} is not a valid rating (0.5 to 5.0 in steps of 0.5)")
    return r


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("user", help="RYM username")
    parser.add_argument("--min", type=rating, default=0.5, help="minimum rating (default 0.5)")
    parser.add_argument("--max", type=rating, default=5.0, help="maximum rating (default 5.0)")
    parser.add_argument("--show", action="store_true", help="always show the browser window")
    parser.add_argument("--refresh", action="store_true", help="ignore the pages saved in the last hours and load them again")
    args = parser.parse_args()
    if args.min > args.max:
        parser.error(f"--min ({args.min}) can't be greater than --max ({args.max})")

    fetcher = Fetcher(headless=not args.show)
    collection = Collection(fetcher, f"{BASE}/collection/{args.user}/r{args.min:.1f}-{args.max:.1f}", args.refresh)
    try:
        first = collection.page(1)
        if first is None:
            sys.exit(f"Couldn't find the collection of '{args.user}' (wrong username or private collection?).")
        if not first[0]:
            sys.exit("The collection is empty for that rating range.")
        choice = random_release(collection)
    finally:
        fetcher.close()

    year = f" ({choice['year']})" if choice["year"] else ""
    print(f"{choice['artist']} - {choice['title']}{year}")
    print(f"Rating: {choice['rating']}")
    print(choice["url"])


if __name__ == "__main__":
    main()
