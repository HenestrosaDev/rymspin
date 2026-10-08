import collections
import random
import time

from conftest import FakeCollection, FakeFetcher, full_pages, release

import rymspin


def titles(picked):
    return [r["title"] for r in picked]


def test_pick_is_uniform_and_skips_missing_slots():
    # 3 pages so the sampling path is used before everything gets loaded.
    counts: collections.Counter[str] = collections.Counter()
    for _ in range(4000):
        picked, _ = rymspin.pick(FakeCollection(full_pages(3, last=2)))
        counts.update(titles(picked))
    assert len(counts) == 52
    assert min(counts.values()) > 30 and max(counts.values()) < 130


def test_pick_returns_different_releases():
    picked, searched_all = rymspin.pick(FakeCollection(full_pages(4)), count=30)
    assert len(set(titles(picked))) == 30
    assert searched_all


def test_pick_with_more_than_available_returns_everything():
    picked, searched_all = rymspin.pick(FakeCollection(full_pages(2, last=3)), count=50)
    assert sorted(titles(picked)) == sorted(r["title"] for page in full_pages(2, last=3) for r in page)
    assert searched_all


def test_pick_applies_match():
    assert titles(rymspin.pick(FakeCollection(full_pages(5)), match=lambda r: r["title"] == "p3-7")[0]) == ["p3-7"]


def test_pick_stops_after_max_pages():
    collection = FakeCollection(full_pages(50))
    picked, searched_all = rymspin.pick(collection, match=lambda r: False, max_pages=4)
    assert picked == [] and not searched_all
    assert len(set(collection.loaded)) == 5  # page 1 plus 4 requests


def test_pick_does_not_count_saved_pages():
    collection = FakeCollection(full_pages(50), saved=range(1, 31))
    rymspin.pick(collection, match=lambda r: False, max_pages=4)
    assert len(set(collection.loaded) - set(range(1, 31))) == 4


def test_pick_uses_every_page_when_all_are_saved():
    collection = FakeCollection(full_pages(50), saved=range(1, 51))
    picked, _ = rymspin.pick(collection, match=lambda r: r["title"] == "p42-3", max_pages=1)
    assert titles(picked) == ["p42-3"]


def test_pick_with_no_match_after_loading_everything():
    assert rymspin.pick(FakeCollection(full_pages(3)), match=lambda r: False) == ([], True)


def test_pick_weighted_prefers_heavier_releases():
    random.seed(0)  # the ratio varies by chance, so make it repeatable
    pages = [[release("good", rating="5.00"), release("bad", rating="0.50")]]
    counts = collections.Counter(
        titles(rymspin.pick(FakeCollection(pages), weight=rymspin.rating_weight)[0])[0] for _ in range(3000)
    )
    assert 8 < counts["good"] / counts["bad"] < 12


def test_release_type():
    assert rymspin.release_type(release("x", kind="ep")) == "ep"


def test_filters():
    match = rymspin.filters(
        types={"album"},
        year_from=1970,
        year_to=1979,
        min_rating=4.0,
        max_rating=5.0,
        skip=[release("seen", year="1975", rating="4.50")["url"]],
    )
    assert match(release("x", year="1975", rating="4.50"))
    assert not match(release("seen", year="1975", rating="4.50"))
    assert not match(release("x", year="1975", rating="4.50", kind="ep"))
    assert not match(release("x", year="1980", rating="4.50"))
    assert not match(release("x", year="1969", rating="4.50"))
    assert not match(release("x", year="", rating="4.50"))
    assert not match(release("x", year="1975", rating="3.50"))
    assert not match(release("x", year="1975", rating="?"))


def test_filters_without_options_match_everything():
    assert rymspin.filters()(release("x", year="", rating="?"))


def test_history_keeps_the_last_picks(monkeypatch):
    monkeypatch.setattr(rymspin, "HISTORY_SIZE", 3)
    history = rymspin.load_history()
    rymspin.save_history(history, "Example_User", [release(str(i)) for i in range(5)])
    saved = rymspin.load_history()["example_user"]
    assert [url.split("/")[-2] for url in saved] == ["2", "3", "4"]


def test_old_data_folder_is_moved(tmp_path, monkeypatch):
    old, new = tmp_path / ".rym-random", tmp_path / ".rymspin"
    (old / "profile").mkdir(parents=True)
    monkeypatch.setattr(rymspin, "OLD_DATA_DIR", old)
    monkeypatch.setattr(rymspin, "DATA_DIR", new)
    rymspin.move_old_data()
    assert (new / "profile").is_dir() and not old.exists()


def test_old_data_folder_is_kept_if_the_new_one_exists(tmp_path, monkeypatch):
    old, new = tmp_path / ".rym-random", tmp_path / ".rymspin"
    old.mkdir()
    new.mkdir()
    monkeypatch.setattr(rymspin, "OLD_DATA_DIR", old)
    monkeypatch.setattr(rymspin, "DATA_DIR", new)
    rymspin.move_old_data()
    assert old.is_dir()


def test_collection_saves_pages_to_disk(fetcher):
    url = "https://rateyourmusic.com/collection/example_user/r0.5-5.0"
    rows, pages = rymspin.Collection(fetcher, url).page(1)
    assert len(rows) == 3 and pages == 12
    assert rymspin.Collection(fetcher, url).page(1) == (rows, pages)
    assert fetcher.urls == [url]


def test_collection_requests_later_pages_by_number(fetcher):
    rymspin.Collection(fetcher, "https://x/collection/u/r0.5-5.0").page(3)
    rymspin.Collection(fetcher, "https://x/collection/u/stag/night/").page(2)
    assert fetcher.urls == ["https://x/collection/u/r0.5-5.0/3", "https://x/collection/u/stag/night/2"]


def test_collection_is_available_only_for_saved_pages(fetcher):
    rymspin.Collection(fetcher, "https://x/c").page(1)
    collection = rymspin.Collection(fetcher, "https://x/c")
    assert collection.is_available(1) and not collection.is_available(2)
    assert len(fetcher.urls) == 1


def test_collection_refresh_ignores_saved_pages(fetcher):
    rymspin.Collection(fetcher, "https://x/c").page(1)
    rymspin.Collection(fetcher, "https://x/c", refresh=True).page(1)
    assert len(fetcher.urls) == 2


def test_collection_reloads_expired_pages(fetcher, monkeypatch):
    rymspin.Collection(fetcher, "https://x/c").page(1)
    now = time.time()
    monkeypatch.setattr(rymspin.time, "time", lambda: now + rymspin.CACHE_TTL + 1)
    rymspin.Collection(fetcher, "https://x/c").page(1)
    assert len(fetcher.urls) == 2


def test_missing_collection_is_none_and_not_saved(cache_dir):
    fetcher = FakeFetcher("<html><body>Not found</body></html>")
    assert rymspin.Collection(fetcher, "https://x/c").page(1) is None
    assert not cache_dir.exists() or not any(cache_dir.iterdir())


def test_choose_returns_different_releases():
    picked = rymspin.choose([release(str(i)) for i in range(5)], 10)
    assert sorted(titles(picked)) == ["0", "1", "2", "3", "4"]


def test_all_rows_reads_every_page():
    rows, requests, complete = rymspin.all_rows(FakeCollection(full_pages(3, last=4)), max_pages=5)
    assert len(rows) == 54 and requests == 2 and complete


def test_all_rows_stops_after_max_pages_and_skips_saved_pages():
    collection = FakeCollection(full_pages(10), saved=[2, 3])
    rows, requests, complete = rymspin.all_rows(collection, max_pages=2)
    assert len(rows) == 5 * 25 and requests == 2 and not complete


def test_shared_releases():
    mine = [release("a", rating="4.00"), release("b")]
    theirs = [release("a", rating="2.00"), release("c")]
    shared = rymspin.shared_releases(mine, theirs, "other_user")
    assert titles(shared) == ["a"]
    assert shared[0]["other"] == {"user": "other_user", "rating": "2.00"}
    assert rymspin.shared_weight(shared[0]) == (0.8 + 0.4) / 2


def test_rating_weight_is_relative_to_the_highest_rating():
    assert rymspin.rating_weight(release("x", rating="2.50")) == 0.5
    assert rymspin.rating_weight(release("x", rating="1.00"), top=1.0) == 1.0
    assert rymspin.rating_weight(release("x", rating="0.50"), top=1.0) == 0.5
    assert rymspin.rating_weight(release("x", rating="?"), top=1.0) == 0.5
