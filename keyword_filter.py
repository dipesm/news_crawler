# =============================================================================
# keyword_filter.py — Keyword matching engine (URL slug + content)
# =============================================================================

import re
from urllib.parse import urlparse, unquote
from config import KEYWORDS, KEYWORD_MATCH, URL_FILTER_STRICT, USE_KEYWORDS
from logger import get_logger

log = get_logger(__name__)

# Compile all keywords once at import time (case-insensitive)
_PATTERNS = [re.compile(re.escape(kw), re.IGNORECASE) for kw in KEYWORDS]


def _matches(text: str) -> bool:
    """Apply KEYWORD_MATCH logic — 'any' (OR) or 'all' (AND)."""
    if not KEYWORDS:
        return True
    if KEYWORD_MATCH == "all":
        return all(p.search(text) for p in _PATTERNS)
    return any(p.search(text) for p in _PATTERNS)


def url_passes(url: str) -> bool:
    """
    Step 1 — URL slug pre-filter. Zero HTTP cost.
    Only active when USE_KEYWORDS=True AND URL_FILTER_STRICT=True.
    URL-decodes the path so Nepali unicode slugs are checked correctly.
    """
    if not USE_KEYWORDS or not URL_FILTER_STRICT:
        return True

    parsed = urlparse(url)
    slug   = unquote(parsed.path + " " + parsed.query)
    passed = _matches(slug)

    if not passed:
        log.debug("URL pre-filter rejected: %s", url)
    return passed


def content_passes(title: str, content: str) -> bool:
    """
    Step 2 — Content post-filter. Called after article is fetched and parsed.
    Only active when USE_KEYWORDS=True.
    Checks combined title + content against all keywords.
    """
    if not USE_KEYWORDS:
        return True

    passed = _matches(f"{title} {content}")
    if not passed:
        log.debug("Content filter rejected: '%s...'", title[:60])
    return passed


def active_keywords() -> list:
    """Return current keyword list — used for startup logging."""
    return list(KEYWORDS)
