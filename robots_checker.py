# =============================================================================
# robots_checker.py — Robots.txt compliance with in-memory TTL cache
# =============================================================================

import time
import urllib.robotparser
from urllib.parse import urlparse
from config import RESPECT_ROBOTS_TXT, ROBOTS_CACHE_TTL
from logger import get_logger

log = get_logger(__name__)

_cache: dict = {}   # domain → {"parser": RobotFileParser, "expires": float}
USER_AGENT = "NewsScraperBot"


def _get_domain(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _load_robots(base_url: str) -> urllib.robotparser.RobotFileParser:
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"{base_url}/robots.txt")
    try:
        rp.read()
    except Exception as e:
        log.debug("Could not read robots.txt for %s: %s", base_url, e)
    return rp


def is_allowed(url: str) -> bool:
    """
    Return True if the URL is allowed to be crawled.
    Always returns True when RESPECT_ROBOTS_TXT is False.
    """
    if not RESPECT_ROBOTS_TXT:
        return True

    base = _get_domain(url)
    now  = time.monotonic()

    if base not in _cache or _cache[base]["expires"] < now:
        _cache[base] = {
            "parser":  _load_robots(base),
            "expires": now + ROBOTS_CACHE_TTL,
        }

    allowed = _cache[base]["parser"].can_fetch(USER_AGENT, url)
    if not allowed:
        log.info("Blocked by robots.txt: %s", url)
    return allowed
