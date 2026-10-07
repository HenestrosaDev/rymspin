import json
import sys

import pytest

import rym_random
from conftest import FakeFetcher, release


def test_search_links_drop_romanized_names():
    links = rym_random.search_links({"artist": "박지하 [Park Jiha]", "title": "Communion"})
    assert links["youtube"] == "https://www.youtube.com/results?search_query=%EB%B0%95%EC%A7%80%ED%95%98+Communion"
    assert links["spotify"].endswith("/search/%EB%B0%95%EC%A7%80%ED%95%98%20Communion")
    assert links["bandcamp"].startswith("https://bandcamp.com/search?q=")


def test_format_release_plain():
    text = rym_random.format_release(release("x", year="1999", rating="4.00"))
    assert text == "A - x (1999)\nRating: 4.00\nhttps://rateyourmusic.com/release/album/a/x/"


def test_format_release_with_details_and_links():
    r = dict(release("x", kind="ep"), cover="https://c/x", rated="2020-01-31", tags=["night"])
    lines = rym_random.format_release(r, details=True, links=True).splitlines()
    assert "Type: ep" in lines and "Rated on: 2020-01-31" in lines and "Tags: night" in lines
    assert "Cover: https://c/x" in lines
    assert [line.split(":")[0] for line in lines[-3:]] == ["Spotify", "YouTube", "Bandcamp"]


@pytest.fixture
def run(fetcher, monkeypatch, capsys):
    """Run main() with the given arguments against the fixture page."""
    monkeypatch.setattr(rym_random, "Fetcher", lambda headless: fetcher)
    fetcher.close = lambda: None
    opened = []
    monkeypatch.setattr(rym_random.webbrowser, "open", opened.append)

    def run(*args):
        monkeypatch.setattr(sys, "argv", ["rym_random.py", "example_user", *args])
        rym_random.main()
        return capsys.readouterr(), opened

    return run


def test_main_prints_a_release(run, monkeypatch):
    # The fixture says there are 12 pages; make it a single one.
    monkeypatch.setattr(rym_random, "last_page", lambda soup: 1)
    (out, err), opened = run()
    assert out.splitlines()[1].startswith("Rating: ")
    assert opened == []


def test_main_json_and_open(run, monkeypatch):
    monkeypatch.setattr(rym_random, "last_page", lambda soup: 1)
    (out, err), opened = run("-n", "3", "--json", "--links", "--open")
    picks = json.loads(out)
    assert sorted(p["title"] for p in picks) == ["First Record", "Split", "Unrated"]
    assert {p["type"] for p in picks} == {"album", "ep", "single"}
    assert all("links" in p for p in picks)
    assert sorted(opened) == sorted(p["url"] for p in picks)


def test_main_reports_when_fewer_releases_match(run, monkeypatch):
    monkeypatch.setattr(rym_random, "last_page", lambda soup: 1)
    (out, err), _ = run("--type", "ep", "-n", "2")
    assert "Only 1 release matches" in err
    assert "Split" in out


def test_main_no_repeat_skips_previous_picks(run, monkeypatch):
    monkeypatch.setattr(rym_random, "last_page", lambda soup: 1)
    titles = set()
    for _ in range(3):
        (out, _), _ = run("--no-repeat", "5", "--json")
        titles.add(json.loads(out)[0]["title"])
    assert titles == {"First Record", "Split", "Unrated"}
    with pytest.raises(SystemExit, match="No release matches"):
        run("--no-repeat", "5")


def test_main_with_other_user(run, fetcher, monkeypatch):
    monkeypatch.setattr(rym_random, "last_page", lambda soup: 1)
    (out, _), _ = run("--with", "other_user", "-n", "3", "--json")
    picks = json.loads(out)
    assert len(picks) == 3
    assert all(p["other"]["user"] == "other_user" for p in picks)
    assert any("/collection/other_user/r0.5-5.0" in url for url in fetcher.urls)


def test_main_with_other_user_shows_both_ratings(run, monkeypatch):
    monkeypatch.setattr(rym_random, "last_page", lambda soup: 1)
    (out, _), _ = run("--with", "other_user", "--type", "ep")
    assert "Rating: 3.00\nRating of other_user: 3.00" in out


def test_main_with_other_user_stops_at_max_pages(run, fetcher):
    # The fixture says there are 12 pages, more than --max-pages allows.
    with pytest.raises(SystemExit, match="Run the same command again"):
        run("--with", "other_user", "--max-pages", "3")
    assert len(fetcher.urls) == 1 + 1 + 3  # page 1 of each user and 3 more


def test_main_with_other_user_without_shared_releases(run, fetcher, monkeypatch):
    monkeypatch.setattr(rym_random, "last_page", lambda soup: 1)
    with pytest.raises(SystemExit, match="No release rated by both"):
        run("--with", "other_user", "--from", "2030")
