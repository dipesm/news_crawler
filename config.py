# =============================================================================
# config.py — Central configuration for the news scraper
# Edit values here. No need to touch any other file.
# =============================================================================

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------
DB_CONFIG = {
    "host":        "localhost",
    "user":        "root",
    "password":    "",
    "database":    "ecn",
    "use_unicode": True,
    # NOTE: Do NOT add "charset": "utf8mb4" here — causes "unknown encoding"
    # error with mysql-connector-python. Charset is set via SQL after connect.
}

# -----------------------------------------------------------------------------
# Scraper behaviour
# -----------------------------------------------------------------------------
MAX_WORKERS           = 50   # parallel threads (increase for speed, decrease to avoid bans)
MAX_RETRIES           = 2    # retry attempts per site before giving up
FETCH_TIMEOUT         = 8    # seconds before a request is considered dead
MAX_ARTICLE_AGE_DAYS  = 1    # skip articles older than this many days
MAX_ARTICLES_PER_SITE = 30   # max article links to process per site per run

# -----------------------------------------------------------------------------
# Keyword filtering
#
# ✅ MAIN SWITCH — only change this one line to toggle modes:
#   USE_KEYWORDS = False  →  collect ALL news (no filtering)
#   USE_KEYWORDS = True   →  only collect articles matching KEYWORDS below
# -----------------------------------------------------------------------------
USE_KEYWORDS = False

KEYWORDS = [
    # English
    "election", "vote", "voting", "ballot", "parliament", "minister",
    "government", "political", "party", "politics", "protest", "corruption",
    "president", "prime-minister", "democracy", "coalition", "senate",
    "congress", "policy", "law", "legislation", "court", "verdict",

    # Nepali (Devanagari)
    "निर्वाचन", "मतदान", "संसद", "मन्त्री", "सरकार", "राजनीति",
    "भ्रष्टाचार", "आन्दोलन", "चुनाव", "प्रधानमन्त्री", "राष्ट्रपति",
    "लोकतन्त्र", "गठबन्धन", "अदालत", "फैसला", "नीति", "कानून",
]

KEYWORD_MATCH     = "any"   # "any" = match at least one  |  "all" = match all
URL_FILTER_STRICT = False   # True  = also pre-filter by URL slug (faster but
                            #         misses sites with numeric URLs /article/123)
                            # False = fetch all URLs, filter at content stage only

# -----------------------------------------------------------------------------
# Rate limiting  (polite crawling — avoids IP bans)
# -----------------------------------------------------------------------------
RATE_LIMIT_ENABLED = True
RATE_LIMIT_CALLS   = 5     # max requests per domain per window
RATE_LIMIT_PERIOD  = 10    # window in seconds

# -----------------------------------------------------------------------------
# Priority sites
# -----------------------------------------------------------------------------
# Sites marked is_priority=1 in the DB are always crawled every run.
# To prevent priority sites from starving normal sites, the scheduler
# interleaves them: for every N normal sites, 1 priority site is inserted.
PRIORITY_INTERLEAVE = 5   # 1 priority site per 5 normal sites in the queue

# -----------------------------------------------------------------------------
# Read/unread
# -----------------------------------------------------------------------------
# Newly scraped articles are always marked unread (is_read=0) by default.
# No config needed — this is enforced in save_articles().

# -----------------------------------------------------------------------------
# Failure tracking
# -----------------------------------------------------------------------------
AUTO_DISABLE_AFTER_FAILURES = 3   # auto-disable site after N consecutive failures
# NOTE: Priority sites are NEVER auto-disabled regardless of failure count

# -----------------------------------------------------------------------------
# Robots.txt compliance
# NOTE: Most Nepali news sites have Disallow: / which blocks all bots.
# Set True only if you want to strictly respect robots.txt.
# -----------------------------------------------------------------------------
RESPECT_ROBOTS_TXT = False
ROBOTS_CACHE_TTL   = 3600   # seconds to cache each site's robots.txt

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
LOG_DIR            = "logs"
LOG_LEVEL          = "INFO"   # DEBUG | INFO | WARNING | ERROR
LOG_RETENTION_DAYS = 14
