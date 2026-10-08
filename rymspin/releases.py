"""Fields of a release dict, as returned by parsing.parse_rows()."""

from .config import BASE


def release_type(release):
    """Type of a release (album, ep, single, comp...), taken from its URL."""
    return release["url"][len(BASE) :].split("/")[2]


def rating_value(release):
    """Rating of a release as a number, or None if it's unknown."""
    try:
        return float(release["rating"])
    except ValueError:
        return None
