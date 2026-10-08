"""Chrome, controlled with Playwright, to load RYM pages past Cloudflare."""

import sys
import time

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from .config import DATA_DIR

PROFILE_DIR = DATA_DIR / "profile"

REQUEST_DELAY = 3  # seconds between page loads; quick bursts get the IP blocked


class Fetcher:
    """Chrome browser with a persistent profile.

    Starts headless; if Cloudflare doesn't let it through, it reopens with a
    visible window so the challenge can be solved by hand. Chrome is only
    launched on the first request, so runs served from the cache don't open it.
    """

    def __init__(self, headless=True):
        self.headless = headless
        self._pw = None
        self._ctx = None
        self._last_request = 0.0

    def _launch(self, headless):
        assert self._pw is not None  # started by get()
        if self._ctx is not None:
            self._ctx.close()
        self.headless = headless
        opts = {
            "channel": "chrome",
            "headless": headless,
            "ignore_default_args": ["--enable-automation"],
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        self._ctx = self._pw.chromium.launch_persistent_context(PROFILE_DIR, **opts)
        if headless:
            # The headless user agent contains "HeadlessChrome", which Cloudflare
            # detects and which invalidates the cookie obtained with a window.
            ua = self._new_page().evaluate("navigator.userAgent")
            if "HeadlessChrome" in ua:
                self._ctx.close()
                opts["user_agent"] = ua.replace("HeadlessChrome", "Chrome")
                self._ctx = self._pw.chromium.launch_persistent_context(PROFILE_DIR, **opts)
        self._page = self._new_page()

    def _new_page(self):
        assert self._ctx is not None
        return self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def get(self, url):
        if self._pw is None:
            self._pw = sync_playwright().start()
            self._launch(self.headless)
        wait = self._last_request + REQUEST_DELAY - time.time()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.time()
        self._page.goto(url)
        # Wait for the Cloudflare challenge to clear. Headless waits briefly
        # and, if it doesn't pass, retries with a window (up to ~60 s, in case
        # the checkbox has to be ticked by hand).
        for _ in range(10 if self.headless else 60):
            if "Just a moment" not in self._page.title():
                break
            self._page.wait_for_timeout(1000)
        else:
            if self.headless:
                print("Cloudflare asks for a verification; opening a window...", file=sys.stderr)
                self._launch(headless=False)
                return self.get(url)
            sys.exit("Couldn't get past the Cloudflare protection.")
        if "IP blocked" in self._page.title():
            sys.exit(
                "RYM has temporarily blocked your IP for loading too many pages. Wait a few hours "
                "(the block lifts by itself) and use fewer pages, e.g. a lower --max-pages."
            )
        self._page.wait_for_load_state("networkidle")
        return BeautifulSoup(self._page.content(), "html.parser")

    def close(self):
        if self._ctx is not None:
            self._ctx.close()
        if self._pw is not None:
            self._pw.stop()
