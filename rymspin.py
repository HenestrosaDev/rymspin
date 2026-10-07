#!/usr/bin/env python3
"""Pick a random release from the ones a Rate Your Music user has rated.

Usage:
    python rymspin.py USER [--min 0.5] [--max 5.0] [-n 1] [--type album ep]
                           [--from 1970] [--to 1979] [--decade 1970s] [--tag TAG]
                           [--rated-from 2015] [--rated-to 2019-06] [--weighted]
                           [--no-repeat 50] [--seed SEED | --daily] [--details]
                           [--links] [--json] [--open] [--show] [--refresh]
                           [--with OTHER_USER | --new-from OTHER_USER]
    python rymspin.py USER --history [20] [--json]

RYM is behind Cloudflare, so a real Chrome controlled with Playwright is used.
The profile is stored in ~/.rymspin/profile/ (or $RYMSPIN_HOME) to reuse the Cloudflare cookie between
runs. The browser runs without a window; one only opens if Cloudflare asks for
a verification (or with --show).
"""

import argparse
import datetime
import hashlib
import json
import os
import random
import re
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote, quote_plus

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = "https://rateyourmusic.com"
PER_PAGE = 25
DATA_DIR = Path(os.environ.get("RYMSPIN_HOME") or Path.home() / ".rymspin")
OLD_DATA_DIR = Path.home() / ".rym-random"  # used before the project was renamed to rymspin
PROFILE_DIR = DATA_DIR / "profile"
CACHE_DIR = DATA_DIR / "cache"
CACHE_TTL = 6 * 3600  # seconds a saved page is reused
OWN_COLLECTION_TTL = 7 * 24 * 3600  # for --new-from, which reads the user's whole collection
CACHE_VERSION = 2  # change when parse_rows() returns different fields
HISTORY_FILE = DATA_DIR / "history.json"
HISTORY_SIZE = 1000  # picks remembered per user
MAX_PAGES = 5  # pages loaded from RYM at most per run when filters skip releases
REQUEST_DELAY = 3  # seconds between page loads; quick bursts get the IP blocked
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
        self._last_request = 0.0

    def _launch(self, headless):
        assert self._pw is not None  # started by get()
        if self._ctx is not None:
            self._ctx.close()
        self.headless = headless
        opts = {
            "channel": "chrome",
            "headless": headless,
            "ignore_default_args": ["--enable-automation"],
            "args": ["--disable-blink-features=AutomationControlled"],
        }
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
        assert self._ctx is not None
        return self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def get(self, url):
        if self._pw is None:
            self._pw = sync_playwright().start()
            self._launch(self.headless)
        wait = self._last_request + REQUEST_DELAY - time.time()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.time()
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
        if "IP blocked" in self._page.title():
            sys.exit(
                "RYM has temporarily blocked your IP for loading too many pages. Wait a few hours "
                "(the block lifts by itself) and use fewer pages, e.g. a lower --max-pages."
            )
        self._page.wait_for_load_state("networkidle")
        return BeautifulSoup(self._page.content(), "html.parser")

    def close(self):
        if self._ctx is not None:
            self._ctx.close()
        if self._pw is not None:
            self._pw.stop()


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
        cover = row.select_one("td.or_q_thumb_album img")
        albums.append(
            {
                "artist": " & ".join(a.get_text(" ", strip=True) for a in artists) or "?",
                "title": album.get_text(" ", strip=True),
                "year": year.get_text(strip=True).strip("()") if year else "",
                "rating": rating["title"].replace(" stars", "") if rating else "?",
                "url": BASE + album["href"],
                "cover": "https:" + cover["src"]
                if cover and cover.get("src", "").startswith("//")
                else (cover.get("src", "") if cover else ""),
                "rated": rated_date(row),
                "tags": [a.get_text(" ", strip=True) for a in row.select("div.or_q_tagcloud a")],
            }
        )
    return albums


MONTHS = {
    m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)
}


def rated_date(row):
    """Date the release was rated, as YYYY-MM-DD, or "" if it's not shown."""
    parts = [row.select_one(f"div.date_element_{p}") for p in ("year", "month", "day")]
    if not all(parts):
        return ""
    year, month, day = (p.get_text(strip=True) for p in parts)
    if month not in MONTHS or not year.isdigit() or not day.isdigit():
        return ""
    return f"{year}-{MONTHS[month]:02d}-{int(day):02d}"


def search_links(release):
    """Search URLs for the release on streaming and shopping sites."""
    # Drop the romanized names RYM adds in brackets, e.g. "박지하 [Park Jiha]".
    artist = re.sub(r"\s*\[[^\]]*\]", "", release["artist"])
    query = f"{artist} {release['title']}".strip()
    return {
        "spotify": f"https://open.spotify.com/search/{quote(query)}",
        "youtube": f"https://www.youtube.com/results?search_query={quote_plus(query)}",
        "bandcamp": f"https://bandcamp.com/search?q={quote_plus(query)}",
    }


def last_page(soup):
    nums = [int(a.get_text()) for a in soup.select("a.navlinknum") if a.get_text().isdigit()]
    return max(nums, default=1)


def release_type(release):
    """Type of a release (album, ep, single, comp...), taken from its URL."""
    return release["url"][len(BASE) :].split("/")[2]


def pick(collection, count=1, match=None, weight=None, max_pages=MAX_PAGES, stable=False):
    """Pick up to `count` different releases at random from the collection.

    Picks a random page and position; if the position doesn't exist (only
    possible on the last page, which is incomplete), the release doesn't pass
    `match`, it's already picked or it loses the `weight` draw (a probability
    from 0 to 1), it picks again. This keeps the choice uniform (or weighted)
    while only loading the pages that are picked. Once every page is loaded,
    it picks directly among the releases left.

    Returns the picks and whether the whole collection was searched; if it
    wasn't, the search stopped after loading `max_pages` pages from RYM (pages
    saved by earlier runs don't count).

    With `stable`, it doesn't pick directly among the releases when every page
    happens to be saved, so the picks only depend on the random state (as set
    by --seed or --daily) and not on which pages earlier runs saved.
    """
    match = match or (lambda release: True)
    weight = weight or (lambda release: 1.0)

    def rows(number):
        page = collection.page(number)
        return page[0] if page else []

    pages = collection.page(1)[1]
    loaded = {1}
    requests = 0
    picked: list[dict] = []
    while len(picked) < count:
        if not stable and len(loaded) < pages and all(collection.is_available(n) for n in range(1, pages + 1)):
            loaded = set(range(1, pages + 1))
        if len(loaded) >= pages:
            left = [r for n in sorted(loaded) for r in rows(n) if match(r) and r not in picked]
            return picked + choose(left, count - len(picked), weight), True
        number = random.randint(1, pages)
        if number not in loaded:
            if not collection.is_available(number):
                if requests >= max_pages:
                    return picked, False
                requests += 1
            loaded.add(number)
        page_rows = rows(number)
        slot = random.randrange(PER_PAGE)
        if slot >= len(page_rows):
            continue
        release = page_rows[slot]
        if release not in picked and match(release) and random.random() < weight(release):
            picked.append(release)
    return picked, True


def choose(releases, count, weight=None):
    """Pick up to `count` different releases from a list, by `weight` if given."""
    weight = weight or (lambda release: 1.0)
    left = list(releases)
    picked: list[dict] = []
    while left and len(picked) < count:
        release = random.choices(left, [weight(r) for r in left])[0]
        picked.append(release)
        left.remove(release)
    return picked


def all_rows(collection, max_pages):
    """Every release in the collection, loading at most `max_pages` pages from RYM.

    Returns the releases, the number of pages loaded from RYM and whether
    every page was read.
    """
    first = collection.page(1)
    if first is None:
        return [], 0, True
    rows, requests = list(first[0]), 0
    for number in range(2, first[1] + 1):
        if not collection.is_available(number):
            if requests >= max_pages:
                return rows, requests, False
            requests += 1
        page = collection.page(number)
        rows += page[0] if page else []
    return rows, requests, True


def shared_releases(mine, theirs, other_user):
    """Releases in both lists, each with the other user's rating added."""
    their_ratings = {r["url"]: r["rating"] for r in theirs}
    return [
        dict(r, other={"user": other_user, "rating": their_ratings[r["url"]]})
        for r in mine
        if r["url"] in their_ratings
    ]


def shared_weight(release):
    """Weight of a shared release: the average of both users' rating weights."""
    return (rating_weight(release) + rating_weight(release["other"])) / 2


def rating_value(release):
    """Rating of a release as a number, or None if it's unknown."""
    try:
        return float(release["rating"])
    except ValueError:
        return None


def rating_weight(release, top=5.0):
    """Probability of keeping a release when picking weighted by rating.

    It's the rating divided by `top`, the highest rating that can be picked, so
    releases rated `top` are always kept. Dividing by 5 when only low ratings
    can be picked would discard most picks, and each discarded pick can load a
    new page.
    """
    return (rating_value(release) or 0.5) / top


def filters(
    types=None, year_from=None, year_to=None, min_rating=None, max_rating=None, skip=(), rated_from=None, rated_to=None
):
    """Build the `match` function of pick() from the command-line filters.

    `rated_from` and `rated_to` are dates as YYYY-MM-DD strings, compared with
    the date each release was rated.
    """
    skip = set(skip)

    def match(release):
        if release["url"] in skip:
            return False
        if types and release_type(release) not in types:
            return False
        if year_from is not None or year_to is not None:
            if not release["year"].isdigit():
                return False
            year = int(release["year"])
            if (year_from is not None and year < year_from) or (year_to is not None and year > year_to):
                return False
        if min_rating is not None or max_rating is not None:
            value = rating_value(release)
            if (
                value is None
                or (min_rating is not None and value < min_rating)
                or (max_rating is not None and value > max_rating)
            ):
                return False
        if rated_from is not None or rated_to is not None:
            rated = release.get("rated", "")
            if (
                not rated
                or (rated_from is not None and rated < rated_from)
                or (rated_to is not None and rated > rated_to)
            ):
                return False
        return True

    return match


def load_history():
    """Picks of each user: {user: [{"url", "artist", "title", "year", "picked"}, ...]}, oldest first."""
    try:
        history = json.loads(HISTORY_FILE.read_text())
    except (OSError, ValueError):
        return {}
    # Earlier versions only saved the URL of each pick.
    return {user: [{"url": e} if isinstance(e, str) else e for e in entries] for user, entries in history.items()}


def save_history(history, user, releases, today=None):
    """Add the picked releases to the user's history, keeping the last HISTORY_SIZE.

    A release already picked on the same day isn't added again, so running
    --daily (or the same --seed) several times doesn't fill the history.
    """
    key = user.lower()
    today = today or datetime.date.today().isoformat()
    entries = history.get(key, [])
    picked_today = {e["url"] for e in entries if e.get("picked") == today}
    new = [
        {"url": r["url"], "artist": r["artist"], "title": r["title"], "year": r["year"], "picked": today}
        for r in releases
        if r["url"] not in picked_today
    ]
    history[key] = (entries + new)[-HISTORY_SIZE:]
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(json.dumps(history, indent=1))
    except OSError:
        pass


def format_history(entries):
    """Text shown for --history: one pick per line, with the date it was picked."""
    lines = []
    for e in entries:
        if "title" in e:
            year = f" ({e['year']})" if e["year"] else ""
            lines.append(f"{e['picked']}  {e['artist']} - {e['title']}{year}  {e['url']}")
        else:
            lines.append(f"{'?':<10}  {e['url']}")
    return "\n".join(lines)


def format_release(release, details=False, links=False):
    """Text shown for a picked release."""
    year = f" ({release['year']})" if release["year"] else ""
    # With --new-from, the rating, date and tags are the other user's.
    by = f" (by {release['rated_by']})" if release.get("rated_by") else ""
    rating_label = f"Rating of {release['rated_by']}" if by else "Rating"
    lines = [f"{release['artist']} - {release['title']}{year}", f"{rating_label}: {release['rating']}"]
    if release.get("other"):
        lines.append(f"Rating of {release['other']['user']}: {release['other']['rating']}")
    if details:
        lines.append(f"Type: {release_type(release)}")
        if release.get("rated"):
            lines.append(f"Rated on{by}: {release['rated']}")
        if release.get("tags"):
            lines.append(f"Tags{by}: {', '.join(release['tags'])}")
        if release.get("cover"):
            lines.append(f"Cover: {release['cover']}")
    lines.append(release["url"])
    if links:
        names = {"spotify": "Spotify", "youtube": "YouTube", "bandcamp": "Bandcamp"}
        lines += [f"{names[site]}: {url}" for site, url in search_links(release).items()]
    return "\n".join(lines)


def rating(value):
    """argparse type for a RYM rating: 0.5 to 5.0 in steps of 0.5."""
    try:
        r = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a number") from None
    if not 0.5 <= r <= 5.0 or r * 2 != int(r * 2):
        raise argparse.ArgumentTypeError(f"{value} is not a valid rating (0.5 to 5.0 in steps of 0.5)")
    return r


def positive(value):
    """argparse type for an integer greater than 0."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a whole number") from None
    if n < 1:
        raise argparse.ArgumentTypeError(f"{value} must be 1 or more")
    return n


def date_range(value):
    """argparse type for a date as YYYY, YYYY-MM or YYYY-MM-DD: its first and last days, as YYYY-MM-DD."""
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            first = datetime.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
        if fmt == "%Y-%m-%d":
            last = first
        elif fmt == "%Y-%m":
            last = (first + datetime.timedelta(days=31)).replace(day=1) - datetime.timedelta(days=1)
        else:
            last = first.replace(month=12, day=31)
        return first.isoformat(), last.isoformat()
    raise argparse.ArgumentTypeError(f"'{value}' is not a date (use YYYY, YYYY-MM or YYYY-MM-DD)")


def decade(value):
    """argparse type for a decade such as 1990s or 1990: its first year."""
    match = re.fullmatch(r"(\d{3}0)s?", value)
    if match is None:
        raise argparse.ArgumentTypeError(f"'{value}' is not a decade (use e.g. 1990s)")
    return int(match.group(1))


def move_old_data():
    """Move the folder of earlier versions to DATA_DIR to keep the Cloudflare session, cache and history."""
    if OLD_DATA_DIR.is_dir() and not DATA_DIR.exists():
        OLD_DATA_DIR.rename(DATA_DIR)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("user", help="RYM username")
    parser.add_argument("--min", type=rating, default=0.5, help="minimum rating (default 0.5)")
    parser.add_argument("--max", type=rating, default=5.0, help="maximum rating (default 5.0)")
    parser.add_argument(
        "-n", "--count", type=positive, default=1, help="number of different releases to pick (default 1)"
    )
    parser.add_argument(
        "--type", nargs="+", metavar="TYPE", help=f"only pick these release types ({', '.join(RELEASE_TYPES)})"
    )
    parser.add_argument(
        "--from", dest="year_from", type=int, metavar="YEAR", help="only pick releases from this year or later"
    )
    parser.add_argument(
        "--to", dest="year_to", type=int, metavar="YEAR", help="only pick releases from this year or earlier"
    )
    parser.add_argument("--decade", type=decade, help="only pick releases from this decade, e.g. 1990s")
    parser.add_argument("--tag", help="only pick releases the user tagged with this tag")
    parser.add_argument(
        "--rated-from",
        type=date_range,
        metavar="DATE",
        help="only pick releases rated on this date (YYYY, YYYY-MM or YYYY-MM-DD) or later",
    )
    parser.add_argument(
        "--rated-to",
        type=date_range,
        metavar="DATE",
        help="only pick releases rated on this date (YYYY, YYYY-MM or YYYY-MM-DD) or earlier",
    )
    parser.add_argument("--weighted", action="store_true", help="make higher-rated releases more likely to be picked")
    parser.add_argument("--no-repeat", type=positive, metavar="N", help="skip the last N releases picked for this user")
    seeds = parser.add_mutually_exclusive_group()
    seeds.add_argument("--seed", help="pick the same releases every time this seed is used (with the same options)")
    seeds.add_argument("--daily", action="store_true", help="pick the same releases all day: a release of the day")
    parser.add_argument(
        "--max-pages",
        type=positive,
        default=MAX_PAGES,
        help=f"pages to load at most when filters skip releases (default {MAX_PAGES})",
    )
    parser.add_argument(
        "--details", action="store_true", help="also show the cover, the date it was rated and the tags"
    )
    parser.add_argument("--links", action="store_true", help="also show search links for Spotify, YouTube and Bandcamp")
    parser.add_argument("--json", action="store_true", help="print the picks as JSON")
    parser.add_argument("--open", action="store_true", help="open the picks on RYM in the web browser")
    others = parser.add_mutually_exclusive_group()
    others.add_argument(
        "--with",
        dest="other_user",
        metavar="OTHER_USER",
        help="only pick releases that OTHER_USER also rated within --min and --max",
    )
    others.add_argument(
        "--new-from",
        metavar="OTHER_USER",
        help="pick releases that OTHER_USER rated within --min and --max and USER hasn't rated",
    )
    parser.add_argument(
        "--history",
        type=positive,
        nargs="?",
        const=20,
        metavar="N",
        help="show the last N releases picked for this user (default 20) instead of picking",
    )
    parser.add_argument("--show", action="store_true", help="always show the browser window")
    parser.add_argument(
        "--refresh", action="store_true", help="ignore the pages saved in the last hours and load them again"
    )
    args = parser.parse_args()
    move_old_data()
    if args.history:
        show_history(args.user, args.history, args.json)
        return
    if args.min > args.max:
        parser.error(f"--min ({args.min}) can't be greater than --max ({args.max})")
    if args.decade is not None:
        if args.year_from is not None or args.year_to is not None:
            parser.error("--decade can't be used with --from or --to")
        args.year_from, args.year_to = args.decade, args.decade + 9
    if args.year_from is not None and args.year_to is not None and args.year_from > args.year_to:
        parser.error(f"--from ({args.year_from}) can't be later than --to ({args.year_to})")
    rated_from = args.rated_from[0] if args.rated_from else None
    rated_to = args.rated_to[1] if args.rated_to else None
    if rated_from and rated_to and rated_from > rated_to:
        parser.error(f"--rated-from ({rated_from}) can't be later than --rated-to ({rated_to})")
    if args.seed is not None and args.no_repeat:
        parser.error("--no-repeat can't be used with --seed, as it would change the picks on each run")
    if args.new_from and args.tag:
        parser.error("--tag can't be used with --new-from")
    types = {t.lower() for t in args.type} if args.type else None
    if types and types - set(RELEASE_TYPES):
        parser.error(
            f"unknown release type: {', '.join(sorted(types - set(RELEASE_TYPES)))} (use {', '.join(RELEASE_TYPES)})"
        )

    today = datetime.date.today().isoformat()
    history = load_history()
    entries = history.get(args.user.lower(), [])
    if args.daily:
        # Only skip picks from before today, so the release of the day stays the same all day.
        entries = [e for e in entries if e.get("picked", "") < today]
    skip = [e["url"] for e in entries[-args.no_repeat :]] if args.no_repeat else ()
    if args.daily:
        random.seed(f"daily {args.user.lower()} {today}")
    elif args.seed is not None:
        random.seed(args.seed)
    seeded = args.daily or args.seed is not None
    if args.tag:
        # Tag pages can't be limited to a rating range, so the range is checked
        # on each release instead.
        url = f"{BASE}/collection/{args.user}/stag/{quote_plus(args.tag.lower())}/"
        min_rating, max_rating = (args.min, args.max) if (args.min, args.max) != (0.5, 5.0) else (None, None)
    else:
        url = f"{BASE}/collection/{args.user}/r{args.min:.1f}-{args.max:.1f}"
        min_rating = max_rating = None
    match = filters(types, args.year_from, args.year_to, min_rating, max_rating, skip, rated_from, rated_to)
    weight = (lambda release: rating_weight(release, args.max)) if args.weighted else None

    fetcher = Fetcher(headless=not args.show)
    try:
        if args.new_from:
            picked, searched_all = pick_new(fetcher, args, match, weight, seeded)
        else:
            collection = Collection(fetcher, url, args.refresh)
            first = collection.page(1)
            if first is None:
                what = f"releases tagged '{args.tag}' by" if args.tag else "the collection of"
                sys.exit(f"Couldn't find {what} '{args.user}' (wrong username, wrong tag or private collection?).")
            if not first[0]:
                sys.exit("The collection is empty for that rating range.")
            if args.other_user:
                picked = pick_shared(fetcher, collection, args, match)
                searched_all = True
            else:
                picked, searched_all = pick(collection, args.count, match, weight, args.max_pages, seeded)
    finally:
        fetcher.close()

    if len(picked) < args.count:
        if searched_all:
            reason = (
                "No release matches the filters."
                if not picked
                else (
                    f"Only {len(picked)} releases match the filters."
                    if len(picked) > 1
                    else "Only 1 release matches the filters."
                )
            )
        else:
            reason = (
                f"Stopped after loading {args.max_pages} pages without finding enough releases that match "
                "the filters; use --max-pages to search more."
            )
        if not picked and args.other_user:
            reason = (
                f"No release rated by both '{args.user}' and '{args.other_user}' in that range matches the filters."
            )
        if not picked and args.new_from and searched_all:
            reason = (
                f"No release rated by '{args.new_from}' in that range and not rated by '{args.user}' "
                "matches the filters."
            )
        if not picked:
            sys.exit(reason)
        print(reason, file=sys.stderr)
    save_history(history, args.user, picked, today)

    if args.json:
        output = [dict(r, type=release_type(r), **({"links": search_links(r)} if args.links else {})) for r in picked]
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for i, choice in enumerate(picked):
            if i:
                print()
            print(format_release(choice, args.details, args.links))
    if args.open:
        for choice in picked:
            webbrowser.open(choice["url"])


def pick_shared(fetcher, collection, args, match):
    """Pick releases both users rated, reading both collections whole.

    Only --max-pages pages are loaded from RYM per run; when the collections
    need more, it exits and the next run goes on from the saved pages.
    """
    other = Collection(fetcher, f"{BASE}/collection/{args.other_user}/r{args.min:.1f}-{args.max:.1f}", args.refresh)
    if other.page(1) is None:
        sys.exit(f"Couldn't find the collection of '{args.other_user}' (wrong username or private collection?).")
    mine, used, mine_done = all_rows(collection, args.max_pages)
    theirs, used_too, theirs_done = ([], 0, False) if not mine_done else all_rows(other, args.max_pages - used)
    if not (mine_done and theirs_done):
        sys.exit(
            f"Loaded {used + used_too} more pages of the two collections, but they have more. Run the same "
            "command again in a while to go on (loaded pages are saved for 6 hours), or use a higher --min "
            "to read fewer pages."
        )
    shared = [r for r in shared_releases(mine, theirs, args.other_user) if match(r)]
    return choose(shared, args.count, shared_weight if args.weighted else None)


def pick_new(fetcher, args, match, weight, stable):
    """Pick releases that args.new_from rated in the range and args.user hasn't rated.

    The user's whole collection is needed to know what they rated, so it's read
    first, loading at most --max-pages pages per run and keeping them for
    OWN_COLLECTION_TTL; when it needs more, it exits and the next run goes on.
    Then the other user's collection is sampled like with pick().
    """
    theirs = Collection(fetcher, f"{BASE}/collection/{args.new_from}/r{args.min:.1f}-{args.max:.1f}", args.refresh)
    first = theirs.page(1)
    if first is None:
        sys.exit(f"Couldn't find the collection of '{args.new_from}' (wrong username or private collection?).")
    if not first[0]:
        sys.exit(f"'{args.new_from}' hasn't rated any release in that rating range.")
    mine = Collection(fetcher, f"{BASE}/collection/{args.user}/r0.5-5.0", args.refresh, OWN_COLLECTION_TTL)
    if mine.page(1) is None:
        sys.exit(f"Couldn't find the collection of '{args.user}' (wrong username or private collection?).")
    rated, used, done = all_rows(mine, args.max_pages)
    if not done:
        sys.exit(
            f"Loaded {used} more pages of the collection of '{args.user}', but it has more. Run the same command "
            "again in a while to go on (the pages of your collection are saved for 7 days)."
        )
    rated_urls = {r["url"] for r in rated}
    picked, searched_all = pick(
        theirs, args.count, lambda r: r["url"] not in rated_urls and match(r), weight, args.max_pages - used, stable
    )
    return [dict(r, rated_by=args.new_from) for r in picked], searched_all


def show_history(user, count, as_json):
    """Print the last `count` releases picked for the user, oldest first."""
    entries = load_history().get(user.lower(), [])[-count:]
    if not entries:
        sys.exit(f"No releases picked for '{user}' yet.")
    print(json.dumps(entries, ensure_ascii=False, indent=2) if as_json else format_history(entries))


if __name__ == "__main__":
    main()
