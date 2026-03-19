# =============================================================================
# rate_limiter.py — Per-domain rate limiting (thread-safe)
# =============================================================================

import time
import threading
from collections import defaultdict, deque
from config import RATE_LIMIT_ENABLED, RATE_LIMIT_CALLS, RATE_LIMIT_PERIOD
from urllib.parse import urlparse

_lock   = threading.Lock()
_calls  = defaultdict(deque)   # domain → deque of timestamps


def _get_domain(url: str) -> str:
    return urlparse(url).netloc


def wait_if_needed(url: str):
    """
    Block the calling thread until it is safe to fetch `url`
    without exceeding RATE_LIMIT_CALLS per RATE_LIMIT_PERIOD seconds
    for that domain. No-op if RATE_LIMIT_ENABLED is False.
    """
    if not RATE_LIMIT_ENABLED:
        return

    domain = _get_domain(url)
    now    = time.monotonic()

    with _lock:
        timestamps = _calls[domain]

        # Drop timestamps outside the current window
        while timestamps and timestamps[0] < now - RATE_LIMIT_PERIOD:
            timestamps.popleft()

        if len(timestamps) >= RATE_LIMIT_CALLS:
            # Must wait until the oldest call falls outside the window
            sleep_for = RATE_LIMIT_PERIOD - (now - timestamps[0]) + 0.05
        else:
            sleep_for = 0

        timestamps.append(now + sleep_for)

    if sleep_for > 0:
        time.sleep(sleep_for)
