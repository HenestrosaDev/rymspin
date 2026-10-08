import argparse

import pytest
from bs4 import BeautifulSoup

from rymspin import cli, parsing


def test_parse_rows(soup):
    rows = parsing.parse_rows(soup)
    assert len(rows) == 3
    assert rows[0] == {
        "artist": "Some Artist [Real Name]",
        "title": "First Record",
        "year": "2018",
        "rating": "4.50",
        "url": "https://rateyourmusic.com/release/album/some-artist/first-record/",
        "cover": "https://cdn.example.net/i/first",
        "rated": "2019-06-08",
        "tags": ["night", "good cover"],
    }


def test_parse_rows_joins_artists_and_handles_missing_year(soup):
    split = parsing.parse_rows(soup)[1]
    assert split["artist"] == "One & Two"
    assert split["year"] == ""


def test_parse_rows_handles_missing_artist_and_rating(soup):
    unrated = parsing.parse_rows(soup)[2]
    assert unrated["artist"] == "?"
    assert unrated["rating"] == "?"
    assert unrated["cover"] == unrated["rated"] == ""
    assert unrated["tags"] == []


def test_parse_rows_without_table():
    assert parsing.parse_rows(BeautifulSoup("<html></html>", "html.parser")) == []


def test_last_page(soup):
    assert parsing.last_page(soup) == 12


def test_last_page_without_pagination():
    assert parsing.last_page(BeautifulSoup("<html></html>", "html.parser")) == 1


@pytest.mark.parametrize("value, expected", [("0.5", 0.5), ("3", 3.0), ("4.5", 4.5), ("5.0", 5.0)])
def test_rating_accepts_valid_values(value, expected):
    assert cli.rating(value) == expected


@pytest.mark.parametrize("value", ["0", "0.3", "5.5", "4.25", "abc", "nan", "inf"])
def test_rating_rejects_invalid_values(value):
    with pytest.raises(argparse.ArgumentTypeError):
        cli.rating(value)
