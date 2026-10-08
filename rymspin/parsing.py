"""Reading the releases out of a RYM collection page."""

import re

from .config import BASE


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


def last_page(soup):
    nums = [int(a.get_text()) for a in soup.select("a.navlinknum") if a.get_text().isdigit()]
    return max(nums, default=1)
