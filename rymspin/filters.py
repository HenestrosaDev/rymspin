"""The `match` function that decides which releases can be picked."""

from .releases import rating_value, release_type


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
