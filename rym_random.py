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
import os
import random
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = "https://rateyourmusic.com"
PER_PAGE = 25
DATA_DIR = Path(os.environ.get("RYM_RANDOM_HOME") or Path.home() / ".rym-random")
PROFILE_DIR = DATA_DIR / "profile"


class Fetcher:
    """Chrome browser with a persistent profile.

    Starts headless; if Cloudflare doesn't let it through, it reopens with a
    visible window so the challenge can be solved by hand.
    """

    def __init__(self, headless=True):
        self._pw = sync_playwright().start()
        self._ctx = None
        self._launch(headless)

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
        self._ctx.close()
        self._pw.stop()


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
    args = parser.parse_args()
    if args.min > args.max:
        parser.error(f"--min ({args.min}) can't be greater than --max ({args.max})")

    collection = f"{BASE}/collection/{args.user}/r{args.min:.1f}-{args.max:.1f}"
    fetcher = Fetcher(headless=not args.show)
    try:
        first = fetcher.get(collection)
        if first.find("table", class_="mbgen") is None:
            sys.exit(f"Couldn't find the collection of '{args.user}' (wrong username or private collection?).")
        cache = {1: parse_rows(first)}
        if not cache[1]:
            sys.exit("The collection is empty for that rating range.")
        pages = last_page(first)

        # Uniform sampling: random page and position; if the position doesn't
        # exist (only possible on the last page, which is incomplete), retry.
        while True:
            page = random.randint(1, pages)
            slot = random.randrange(PER_PAGE)
            if page not in cache:
                cache[page] = parse_rows(fetcher.get(f"{collection}/{page}"))
            if slot < len(cache[page]):
                choice = cache[page][slot]
                break
    finally:
        fetcher.close()

    year = f" ({choice['year']})" if choice["year"] else ""
    print(f"{choice['artist']} - {choice['title']}{year}")
    print(f"Rating: {choice['rating']}")
    print(choice["url"])

if __name__ == "__main__":
    main()
