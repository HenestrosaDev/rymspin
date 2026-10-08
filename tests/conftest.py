from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from rymspin import collection, history

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def soup():
    return BeautifulSoup((FIXTURES / "collection.html").read_text(), "html.parser")


@pytest.fixture(autouse=True)
def cache_dir(tmp_path, monkeypatch):
    """Keep every test's saved pages in its own temporary folder."""
    monkeypatch.setattr(collection, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(history, "HISTORY_FILE", tmp_path / "history.json")
    return tmp_path / "cache"


class FakeFetcher:
    """Serves the fixture page for every URL and records the requests."""

    def __init__(self, html):
        self.html = html
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return BeautifulSoup(self.html, "html.parser")


@pytest.fixture
def fetcher():
    return FakeFetcher((FIXTURES / "collection.html").read_text())


class FakeCollection:
    """Collection with the given pages of rows, without any requests."""

    def __init__(self, pages, saved=()):
        self.pages = pages
        self.saved = set(saved)
        self.loaded = []

    def page(self, number):
        self.loaded.append(number)
        return self.pages[number - 1], len(self.pages)

    def is_available(self, number):
        return number in self.saved or number in self.loaded


def release(url, year="2000", rating="3.00", kind="album"):
    return {
        "artist": "A",
        "title": url,
        "year": year,
        "rating": rating,
        "url": f"https://rateyourmusic.com/release/{kind}/a/{url}/",
    }


def full_pages(count, last=25):
    """Pages of releases named p<page>-<position>, the last one with `last` releases."""
    return [[release(f"p{p}-{i}") for i in range(25 if p < count else last)] for p in range(1, count + 1)]
