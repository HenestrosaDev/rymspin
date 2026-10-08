"""Releases picked in earlier runs, used by --no-repeat and --history."""

import datetime
import json

from .config import DATA_DIR

HISTORY_FILE = DATA_DIR / "history.json"

HISTORY_SIZE = 1000  # picks remembered per user


def load_history():
    """Picks of each user: {user: [{"url", "artist", "title", "year", "picked"}, ...]}, oldest first."""
    try:
        return json.loads(HISTORY_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_history(history, user, releases, today=None):
    """Add the picked releases to the user's history, keeping the last HISTORY_SIZE.

    A release already picked on the same day isn't added again, so running
    --daily (or the same --seed) several times doesn't fill the history.
    """
    key = user.lower()
    today = today or datetime.date.today().isoformat()
    entries = history.get(key, [])
    picked_today = {e["url"] for e in entries if e.get("picked") == today}
    new = [
        {"url": r["url"], "artist": r["artist"], "title": r["title"], "year": r["year"], "picked": today}
        for r in releases
        if r["url"] not in picked_today
    ]
    history[key] = (entries + new)[-HISTORY_SIZE:]
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(json.dumps(history, indent=1))
    except OSError:
        pass
