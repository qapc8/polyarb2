"""Time utilities used across the project."""

from __future__ import annotations

import time
from datetime import datetime, timezone


def now_ms() -> int:
    """Return the current time in milliseconds since the epoch."""

    return int(time.time() * 1000)


def to_datetime(ms: int) -> datetime:
    """Convert milliseconds since epoch to :class:`datetime`."""

    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def ms_since(ts_ms: int) -> int:
    """Return milliseconds elapsed since ``ts_ms``."""

    return now_ms() - ts_ms
