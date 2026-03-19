# =============================================================================
# main.py — Entry point
# =============================================================================

import argparse
from logger import get_logger
from scraper_manager import ScraperManager
from keyword_filter import active_keywords
import config

log = get_logger("main")


def main():
    parser = argparse.ArgumentParser(description="Nepal News Scraper")
    parser.add_argument("--from-id", type=int, default=None, help="Start site ID (inclusive)")
    parser.add_argument("--to-id",   type=int, default=None, help="End site ID (inclusive)")
    parser.add_argument("--latest",  type=int, default=config.MAX_ARTICLES_PER_SITE,
                        help=f"Max articles per site (default: {config.MAX_ARTICLES_PER_SITE})")
    parser.add_argument("--workers", type=int, default=None,
                        help=f"Override MAX_WORKERS (default: {config.MAX_WORKERS})")
    parser.add_argument("--days",    type=int, default=None,
                        help=f"Override MAX_ARTICLE_AGE_DAYS (default: {config.MAX_ARTICLE_AGE_DAYS})")
    args = parser.parse_args()

    # Runtime overrides
    if args.workers:
        config.MAX_WORKERS = args.workers
    if args.days:
        config.MAX_ARTICLE_AGE_DAYS = args.days

    # Startup summary
    kws = active_keywords()
    log.info("=" * 60)
    log.info("Nepal News Scraper starting")
    log.info("  Workers    : %d", config.MAX_WORKERS)
    log.info("  Max age    : %d day(s)", config.MAX_ARTICLE_AGE_DAYS)
    log.info("  Latest     : %d articles/site", args.latest)
    log.info("  Robots.txt : %s", "respected" if config.RESPECT_ROBOTS_TXT else "ignored")
    if config.USE_KEYWORDS:
        log.info("  Mode       : KEYWORD FILTER (%d keywords, match=%s, url_strict=%s)",
                 len(kws), config.KEYWORD_MATCH, config.URL_FILTER_STRICT)
        log.info("  Keywords   : %s", ", ".join(kws[:10]) + (" ..." if len(kws) > 10 else ""))
    else:
        log.info("  Mode       : ALL NEWS (keyword filter OFF)")
    if args.from_id and args.to_id:
        log.info("  Range      : ID %d – %d", args.from_id, args.to_id)
    else:
        log.info("  Range      : ALL active sites")
    log.info("=" * 60)

    manager = ScraperManager()
    total   = manager.run_scrapers(
        latest_n=args.latest,
        id_from=args.from_id,
        id_to=args.to_id,
    )

    log.info("=" * 60)
    log.info("Done. Total articles saved: %d", total)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
