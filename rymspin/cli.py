"""Pick a random release from the ones a Rate Your Music user has rated.

Usage:
    rymspin USER [--min 0.5] [--max 5.0] [-n 1] [--type album ep]
                 [--from 1970] [--to 1979] [--decade 1970s] [--tag TAG]
                 [--rated-from 2015] [--rated-to 2019-06] [--weighted]
                 [--no-repeat 50] [--seed SEED | --daily] [--max-pages 5]
                 [--details] [--links] [--json] [--open] [--show] [--refresh]
                 [--with OTHER_USER | --new-from OTHER_USER]
    rymspin USER --history [20] [--json]

RYM is behind Cloudflare, so a real Chrome controlled with Playwright is used.
The profile is stored in ~/.rymspin/profile/ (or $RYMSPIN_HOME) to reuse the
Cloudflare cookie between runs. The browser runs without a window; one only
opens if Cloudflare asks for a verification (or with --show).
"""

import argparse
import datetime
import json
import random
import re
import sys
import webbrowser
from urllib.parse import quote_plus

from .collection import OWN_COLLECTION_TTL, Collection
from .config import BASE, MAX_PAGES, RELEASE_TYPES
from .fetcher import Fetcher
from .filters import filters
from .history import load_history, save_history
from .output import format_history, format_release, search_links
from .picking import all_rows, choose, pick, rating_weight, shared_releases, shared_weight
from .releases import release_type


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


def build_parser():
    parser = argparse.ArgumentParser(
        prog="rymspin", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
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
    return parser


def check_args(parser, args):
    """Reject options that can't be used together, and turn some into plain values.

    --decade becomes --from and --to, --type a set of lowercase types (or
    None), and --rated-from and --rated-to YYYY-MM-DD strings (or None).
    """
    if args.min > args.max:
        parser.error(f"--min ({args.min}) can't be greater than --max ({args.max})")
    if args.decade is not None:
        if args.year_from is not None or args.year_to is not None:
            parser.error("--decade can't be used with --from or --to")
        args.year_from, args.year_to = args.decade, args.decade + 9
    if args.year_from is not None and args.year_to is not None and args.year_from > args.year_to:
        parser.error(f"--from ({args.year_from}) can't be later than --to ({args.year_to})")
    args.rated_from = args.rated_from[0] if args.rated_from else None
    args.rated_to = args.rated_to[1] if args.rated_to else None
    if args.rated_from and args.rated_to and args.rated_from > args.rated_to:
        parser.error(f"--rated-from ({args.rated_from}) can't be later than --rated-to ({args.rated_to})")
    if args.seed is not None and args.no_repeat:
        parser.error("--no-repeat can't be used with --seed, as it would change the picks on each run")
    if args.new_from and args.tag:
        parser.error("--tag can't be used with --new-from")
    args.type = {t.lower() for t in args.type} if args.type else None
    if args.type and args.type - set(RELEASE_TYPES):
        unknown = ", ".join(sorted(args.type - set(RELEASE_TYPES)))
        parser.error(f"unknown release type: {unknown} (use {', '.join(RELEASE_TYPES)})")


def skipped_urls(args, entries, today):
    """URLs of the earlier picks that --no-repeat skips."""
    if not args.no_repeat:
        return ()
    if args.daily:
        # Only skip picks from before today, so the release of the day stays the same all day.
        entries = [e for e in entries if e.get("picked", "") < today]
    return [e["url"] for e in entries[-args.no_repeat :]]


def seed_random(args, today):
    """Seed the random choices for --daily and --seed, and return whether they're seeded."""
    if args.daily:
        random.seed(f"daily {args.user.lower()} {today}")
    elif args.seed is not None:
        random.seed(args.seed)
    return args.daily or args.seed is not None


def collection_url(args):
    """URL of the user's collection to pick from, and the rating range left to check on each release."""
    if args.tag:
        # Tag pages can't be limited to a rating range, so the range is checked
        # on each release instead.
        url = f"{BASE}/collection/{args.user}/stag/{quote_plus(args.tag.lower())}/"
        return url, ((args.min, args.max) if (args.min, args.max) != (0.5, 5.0) else (None, None))
    return f"{BASE}/collection/{args.user}/r{args.min:.1f}-{args.max:.1f}", (None, None)


def pick_releases(args, url, match, weight, stable):
    """Load the collections needed and pick; returns the picks and whether everything was searched."""
    fetcher = Fetcher(headless=not args.show)
    try:
        if args.new_from:
            return pick_new(fetcher, args, match, weight, stable)
        collection = Collection(fetcher, url, args.refresh)
        first = collection.page(1)
        if first is None:
            what = f"releases tagged '{args.tag}' by" if args.tag else "the collection of"
            sys.exit(f"Couldn't find {what} '{args.user}' (wrong username, wrong tag or private collection?).")
        if not first[0]:
            sys.exit("The collection is empty for that rating range.")
        if args.other_user:
            return pick_shared(fetcher, collection, args, match), True
        return pick(collection, args.count, match, weight, args.max_pages, stable)
    finally:
        fetcher.close()


def shortfall_message(args, picked, searched_all):
    """Why fewer releases than --count were picked."""
    if not picked and args.other_user:
        return f"No release rated by both '{args.user}' and '{args.other_user}' in that range matches the filters."
    if not picked and args.new_from and searched_all:
        return (
            f"No release rated by '{args.new_from}' in that range and not rated by '{args.user}' matches the filters."
        )
    if not searched_all:
        return (
            f"Stopped after loading {args.max_pages} pages without finding enough releases that match "
            "the filters; use --max-pages to search more."
        )
    if not picked:
        return "No release matches the filters."
    if len(picked) == 1:
        return "Only 1 release matches the filters."
    return f"Only {len(picked)} releases match the filters."


def print_picks(picked, args):
    if args.json:
        output = [dict(r, type=release_type(r), **({"links": search_links(r)} if args.links else {})) for r in picked]
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    for i, choice in enumerate(picked):
        if i:
            print()
        print(format_release(choice, args.details, args.links))


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.history:
        show_history(args.user, args.history, args.json)
        return
    check_args(parser, args)

    today = datetime.date.today().isoformat()
    history = load_history()
    skip = skipped_urls(args, history.get(args.user.lower(), []), today)
    stable = seed_random(args, today)
    url, (min_rating, max_rating) = collection_url(args)
    match = filters(
        args.type, args.year_from, args.year_to, min_rating, max_rating, skip, args.rated_from, args.rated_to
    )
    weight = (lambda release: rating_weight(release, args.max)) if args.weighted else None

    picked, searched_all = pick_releases(args, url, match, weight, stable)
    if len(picked) < args.count:
        reason = shortfall_message(args, picked, searched_all)
        if not picked:
            sys.exit(reason)
        print(reason, file=sys.stderr)
    save_history(history, args.user, picked, today)

    print_picks(picked, args)
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
