"""Choosing releases at random from collections, uniformly or weighted by rating."""

import random

from .config import MAX_PAGES, PER_PAGE
from .releases import rating_value


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


def rating_weight(release, top=5.0):
    """Probability of keeping a release when picking weighted by rating.

    It's the rating divided by `top`, the highest rating that can be picked, so
    releases rated `top` are always kept. Dividing by 5 when only low ratings
    can be picked would discard most picks, and each discarded pick can load a
    new page.
    """
    return (rating_value(release) or 0.5) / top
