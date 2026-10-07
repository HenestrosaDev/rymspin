import collections
import time

import rym_random
from conftest import FakeCollection, FakeFetcher


def test_random_release_is_uniform_and_skips_missing_slots():
    pages = [[{"url": f"p1-{i}"} for i in range(25)], [{"url": "p2-0"}, {"url": "p2-1"}]]
    counts = collections.Counter(rym_random.random_release(FakeCollection(pages))["url"] for _ in range(27000))
    assert len(counts) == 27
    assert min(counts.values()) > 700 and max(counts.values()) < 1300


def test_collection_saves_pages_to_disk(fetcher):
    url = "https://rateyourmusic.com/collection/example_user/r0.5-5.0"
    rows, pages = rym_random.Collection(fetcher, url).page(1)
    assert len(rows) == 3 and pages == 12
    assert rym_random.Collection(fetcher, url).page(1) == (rows, pages)
    assert fetcher.urls == [url]


def test_collection_requests_later_pages_by_number(fetcher):
    rym_random.Collection(fetcher, "https://x/collection/u/r0.5-5.0").page(3)
    assert fetcher.urls == ["https://x/collection/u/r0.5-5.0/3"]


def test_collection_refresh_ignores_saved_pages(fetcher):
    rym_random.Collection(fetcher, "https://x/c").page(1)
    rym_random.Collection(fetcher, "https://x/c", refresh=True).page(1)
    assert len(fetcher.urls) == 2


def test_collection_reloads_expired_pages(fetcher, monkeypatch):
    rym_random.Collection(fetcher, "https://x/c").page(1)
    now = time.time()
    monkeypatch.setattr(rym_random.time, "time", lambda: now + rym_random.CACHE_TTL + 1)
    rym_random.Collection(fetcher, "https://x/c").page(1)
    assert len(fetcher.urls) == 2


def test_missing_collection_is_none_and_not_saved(cache_dir):
    fetcher = FakeFetcher("<html><body>Not found</body></html>")
    assert rym_random.Collection(fetcher, "https://x/c").page(1) is None
    assert not cache_dir.exists() or not any(cache_dir.iterdir())
