from pathlib import Path

import pytest
from bs4 import BeautifulSoup

import rym_random

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def soup():
    return BeautifulSoup((FIXTURES / "collection.html").read_text(), "html.parser")


@pytest.fixture(autouse=True)
def cache_dir(tmp_path, monkeypatch):
    """Keep every test's saved pages in its own temporary folder."""
    monkeypatch.setattr(rym_random, "CACHE_DIR", tmp_path / "cache")
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

    def __init__(self, pages):
        self.pages = pages
        self.loaded = []

    def page(self, number):
        self.loaded.append(number)
        return self.pages[number - 1], len(self.pages)
