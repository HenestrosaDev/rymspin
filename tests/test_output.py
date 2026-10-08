import json
import sys

import pytest
from conftest import FIXTURES, FakeFetcher, release

from rymspin import cli, history, output, parsing


def test_search_links_drop_romanized_names():
    links = output.search_links({"artist": "박지하 [Park Jiha]", "title": "Communion"})
    assert links["youtube"] == "https://www.youtube.com/results?search_query=%EB%B0%95%EC%A7%80%ED%95%98+Communion"
    assert links["spotify"].endswith("/search/%EB%B0%95%EC%A7%80%ED%95%98%20Communion")
    assert links["bandcamp"].startswith("https://bandcamp.com/search?q=")


def test_format_release_plain():
    text = output.format_release(release("x", year="1999", rating="4.00"))
    assert text == "A - x (1999)\nRating: 4.00\nhttps://rateyourmusic.com/release/album/a/x/"


def test_format_release_with_details_and_links():
    r = dict(release("x", kind="ep"), cover="https://c/x", rated="2020-01-31", tags=["night"])
    lines = output.format_release(r, details=True, links=True).splitlines()
    assert "Type: ep" in lines and "Rated on: 2020-01-31" in lines and "Tags: night" in lines
    assert "Cover: https://c/x" in lines
    assert [line.split(":")[0] for line in lines[-3:]] == ["Spotify", "YouTube", "Bandcamp"]


@pytest.fixture
def run(fetcher, monkeypatch, capsys):
    """Run main() with the given arguments against the fixture page."""
    monkeypatch.setattr(cli, "Fetcher", lambda headless: fetcher)
    fetcher.close = lambda: None
    opened: list[str] = []
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)

    def run(*args):
        monkeypatch.setattr(sys, "argv", ["rymspin", "example_user", *args])
        cli.main()
        return capsys.readouterr(), opened

    return run


def test_main_prints_a_release(run, monkeypatch):
    # The fixture says there are 12 pages; make it a single one.
    monkeypatch.setattr(parsing, "last_page", lambda soup: 1)
    (out, _), opened = run()
    assert out.splitlines()[1].startswith("Rating: ")
    assert opened == []


def test_main_json_and_open(run, monkeypatch):
    monkeypatch.setattr(parsing, "last_page", lambda soup: 1)
    (out, _), opened = run("-n", "3", "--json", "--links", "--open")
    picks = json.loads(out)
    assert sorted(p["title"] for p in picks) == ["First Record", "Split", "Unrated"]
    assert {p["type"] for p in picks} == {"album", "ep", "single"}
    assert all("links" in p for p in picks)
    assert sorted(opened) == sorted(p["url"] for p in picks)


def test_main_reports_when_fewer_releases_match(run, monkeypatch):
    monkeypatch.setattr(parsing, "last_page", lambda soup: 1)
    (out, err), _ = run("--type", "ep", "-n", "2")
    assert "Only 1 release matches" in err
    assert "Split" in out


def test_main_no_repeat_skips_previous_picks(run, monkeypatch):
    monkeypatch.setattr(parsing, "last_page", lambda soup: 1)
    titles = set()
    for _ in range(3):
        (out, _), _ = run("--no-repeat", "5", "--json")
        titles.add(json.loads(out)[0]["title"])
    assert titles == {"First Record", "Split", "Unrated"}
    with pytest.raises(SystemExit, match="No release matches"):
        run("--no-repeat", "5")


def test_main_with_other_user(run, fetcher, monkeypatch):
    monkeypatch.setattr(parsing, "last_page", lambda soup: 1)
    (out, _), _ = run("--with", "other_user", "-n", "3", "--json")
    picks = json.loads(out)
    assert len(picks) == 3
    assert all(p["other"]["user"] == "other_user" for p in picks)
    assert any("/collection/other_user/r0.5-5.0" in url for url in fetcher.urls)


def test_main_with_other_user_shows_both_ratings(run, monkeypatch):
    monkeypatch.setattr(parsing, "last_page", lambda soup: 1)
    (out, _), _ = run("--with", "other_user", "--type", "ep")
    assert "Rating: 3.00\nRating of other_user: 3.00" in out


def test_main_with_other_user_stops_at_max_pages(run, fetcher):
    # The fixture says there are 12 pages, more than --max-pages allows.
    with pytest.raises(SystemExit, match="Run the same command again"):
        run("--with", "other_user", "--max-pages", "3")
    assert len(fetcher.urls) == 1 + 1 + 3  # page 1 of each user and 3 more


def test_main_with_other_user_without_shared_releases(run, fetcher, monkeypatch):
    monkeypatch.setattr(parsing, "last_page", lambda soup: 1)
    with pytest.raises(SystemExit, match="No release rated by both"):
        run("--with", "other_user", "--from", "2030")


def test_main_history_shows_previous_picks_without_loading_pages(run, fetcher, monkeypatch):
    monkeypatch.setattr(parsing, "last_page", lambda soup: 1)
    run("-n", "3")
    fetcher.urls.clear()
    (out, _), _ = run("--history")
    lines = out.splitlines()
    assert len(lines) == 3 and all("https://rateyourmusic.com/release/" in line for line in lines)
    assert fetcher.urls == []
    (out, _), _ = run("--history", "1", "--json")
    assert len(json.loads(out)) == 1


def test_main_history_without_picks(run):
    with pytest.raises(SystemExit, match="No releases picked"):
        run("--history")


def test_main_daily_keeps_the_same_pick_all_day(run, monkeypatch):
    monkeypatch.setattr(parsing, "last_page", lambda soup: 1)
    picks = {run("--daily", "--no-repeat", "5")[0][0] for _ in range(5)}
    assert len(picks) == 1
    assert len(history.load_history()["example_user"]) == 1


def test_main_seed_repeats_the_picks(run, monkeypatch):
    monkeypatch.setattr(parsing, "last_page", lambda soup: 1)
    assert run("--seed", "x", "-n", "2")[0][0] == run("--seed", "x", "-n", "2")[0][0]


def test_main_seed_and_no_repeat_are_rejected(run):
    with pytest.raises(SystemExit):
        run("--seed", "x", "--no-repeat", "5")


def test_main_decade(run, monkeypatch):
    monkeypatch.setattr(parsing, "last_page", lambda soup: 1)
    (out, _), _ = run("--decade", "2010s", "-n", "3", "--json")
    assert [p["title"] for p in json.loads(out)] == ["First Record"]
    with pytest.raises(SystemExit):
        run("--decade", "2010s", "--from", "2012")


def test_main_rated_from_and_to(run, monkeypatch):
    monkeypatch.setattr(parsing, "last_page", lambda soup: 1)
    (out, _), _ = run("--rated-from", "2019-07", "--rated-to", "2020", "-n", "3", "--json")
    assert [p["title"] for p in json.loads(out)] == ["Split"]
    with pytest.raises(SystemExit):
        run("--rated-from", "2020", "--rated-to", "2019")


class TwoUserFetcher(FakeFetcher):
    """Serves the fixture page for other_user and the same page without "First Record" for example_user."""

    def get(self, url):
        soup = super().get(url)
        if "/example_user/" in url:
            soup.find("tr", id="page_catalog_item_101").decompose()
        return soup

    def close(self):
        pass


@pytest.fixture
def two_users(monkeypatch):
    fetcher = TwoUserFetcher((FIXTURES / "collection.html").read_text())
    monkeypatch.setattr(cli, "Fetcher", lambda headless: fetcher)
    monkeypatch.setattr(parsing, "last_page", lambda soup: 1)
    return fetcher


def test_main_new_from_picks_releases_the_user_has_not_rated(run, two_users):
    (out, err), _ = run("--new-from", "other_user", "-n", "3", "--json")
    picks = json.loads(out)
    assert [p["title"] for p in picks] == ["First Record"]
    assert picks[0]["rated_by"] == "other_user"
    assert "Only 1 release matches" in err
    assert any("/collection/example_user/r0.5-5.0" in url for url in two_users.urls)
    (out, _), _ = run("--new-from", "other_user", "--details")
    assert "Rating of other_user: 4.50" in out and "Rated on (by other_user): 2019-06-08" in out


def test_main_new_from_without_new_releases(run, two_users):
    with pytest.raises(SystemExit, match="not rated by 'example_user'"):
        run("--new-from", "other_user", "--type", "ep")


def test_main_new_from_stops_at_max_pages(run, fetcher, monkeypatch):
    # The fixture says there are 12 pages, more than --max-pages allows.
    with pytest.raises(SystemExit, match="Run the same command again"):
        run("--new-from", "other_user", "--max-pages", "3")
    assert len(fetcher.urls) == 1 + 1 + 3  # page 1 of each user and 3 more of example_user


def test_main_new_from_and_tag_are_rejected(run):
    with pytest.raises(SystemExit):
        run("--new-from", "other_user", "--tag", "night")
