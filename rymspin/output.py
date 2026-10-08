"""Text and links shown for the picked releases."""

import re
from urllib.parse import quote, quote_plus

from .releases import release_type


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


def format_history(entries):
    """Text shown for --history: one pick per line, with the date it was picked."""
    lines = []
    for e in entries:
        year = f" ({e['year']})" if e["year"] else ""
        lines.append(f"{e['picked']}  {e['artist']} - {e['title']}{year}  {e['url']}")
    return "\n".join(lines)
