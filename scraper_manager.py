# =============================================================================
# scraper_manager.py
# =============================================================================

import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from config import MAX_WORKERS, MAX_RETRIES
from logger import get_logger
from scrapers.generic_scraper import GenericScraper, DeadSiteError
from database import (
    get_active_sites,
    get_active_sites_by_range,
    get_active_sites_interleaved,
    record_site_failure,
    record_site_success,
    clear_site_selectors,
    save_articles,
    save_scrape_run,
)

log = get_logger(__name__)


class ScraperManager:

    def scrape_single_site(self, site, latest_n):
        site_id   = site["id"]
        site_name = site["name"]
        delay     = 2   # base delay for exponential backoff (doubles each retry)

        for attempt in range(MAX_RETRIES):
            try:
                log.info("[%s] Scraping %s (attempt %d)", site_id, site_name, attempt + 1)

                scraper            = GenericScraper(site)
                articles, zero_reason = scraper.scrape(latest_n=latest_n)

                if articles:
                    # ✅ Articles found — save and record success
                    save_articles(articles)
                    record_site_success(site_id)

                elif zero_reason == "ALL_DUPLICATE":
                    # ✅ Healthy — all links already in DB, nothing new to save
                    # Reset failure streak (site is working fine)
                    record_site_success(site_id)
                    log.info("[%s] %s — up to date (all duplicates)", site_id, site_name)

                elif zero_reason and zero_reason.startswith("ALL_TOO_OLD"):
                    # ⚠ Site reachable and selector works, but all articles
                    # are older than MAX_ARTICLE_AGE_DAYS. Not a selector
                    # problem — could be a slow-publishing site. Soft success.
                    record_site_success(site_id)
                    log.info("[%s] %s — all articles too old: %s", site_id, site_name, zero_reason)

                elif zero_reason and zero_reason.startswith("NO_LINKS"):
                    # ✗ article_selector matches nothing.
                    # Clear DB + retry immediately with force_redetect=True
                    # so we don't have to wait for the next full run.
                    if not getattr(scraper, '_redetected', False):
                        log.warning("[%s] %s — article_selector broken, re-detecting now…",
                                    site_id, site_name)
                        clear_site_selectors(site_id)
                        scraper.clear_selectors()
                        scraper._redetected = True
                        articles2, reason2 = scraper.scrape(latest_n=latest_n)
                        if articles2:
                            save_articles(articles2)
                            record_site_success(site_id)
                            log.info("[%s] %s — re-detection succeeded, %d articles",
                                     site_id, site_name, len(articles2))
                            return len(articles2)
                        else:
                            record_site_failure(site_id,
                                f"article_selector broken even after re-detection. {reason2}")
                            log.warning("[%s] %s — re-detection also failed: %s",
                                        site_id, site_name, reason2)
                    else:
                        record_site_failure(site_id,
                            "article_selector matched 0 links — re-detection also failed")

                elif zero_reason and zero_reason.startswith("SELECTOR_MISMATCH"):
                    # ✗ title/content selectors failed.
                    # Clear DB + retry immediately with force_redetect=True.
                    if not getattr(scraper, '_redetected', False):
                        log.warning("[%s] %s — selectors broken, re-detecting now…",
                                    site_id, site_name)
                        clear_site_selectors(site_id)
                        scraper.clear_selectors()
                        scraper._redetected = True
                        articles2, reason2 = scraper.scrape(latest_n=latest_n)
                        if articles2:
                            save_articles(articles2)
                            record_site_success(site_id)
                            log.info("[%s] %s — re-detection succeeded, %d articles",
                                     site_id, site_name, len(articles2))
                            return len(articles2)
                        else:
                            record_site_failure(site_id,
                                f"selectors broken even after re-detection. {reason2}")
                            log.warning("[%s] %s — re-detection also failed: %s",
                                        site_id, site_name, reason2)
                    else:
                        record_site_failure(site_id,
                            f"selectors broken — re-detection also failed. {zero_reason}")

                elif zero_reason and zero_reason.startswith("ALL_KEYWORD_FILTERED"):
                    # ✅ Working fine, keyword filter excluded everything
                    record_site_success(site_id)
                    log.info("[%s] %s — keyword filtered: %s", site_id, site_name, zero_reason)

                else:
                    # Unknown zero reason — soft failure, investigate
                    record_site_failure(site_id,
                        f"0 articles, unknown reason: {zero_reason}")
                    log.warning("[%s] %s — 0 articles: %s", site_id, site_name, zero_reason)

                return len(articles)

            except DeadSiteError as e:
                # Domain does not resolve — disable immediately, no retry
                # (but never disable priority sites)
                log.warning("[%s] Dead domain: %s", site_id, site_name)
                is_prio = site.get("is_priority", 0)
                record_site_failure(site_id, str(e),
                                    force_disable=not is_prio)
                return 0

            except Exception as e:
                log.warning("[%s] Attempt %d failed for %s: %s",
                            site_id, attempt + 1, site_name, e)
                record_site_failure(site_id, str(e))

                if attempt < MAX_RETRIES - 1:
                    log.debug("Backing off %ds before retry...", delay)
                    time.sleep(delay)
                    delay *= 2   # exponential backoff: 2s → 4s

        log.error("[%s] Gave up on %s after %d attempts", site_id, site_name, MAX_RETRIES)
        return 0

    def run_scrapers(self, latest_n=20, id_from=None, id_to=None):

        if id_from is not None and id_to is not None:
            sites = get_active_sites_by_range(id_from, id_to)
            log.info("Scraping sites ID %d–%d → %d active sites found",
                     id_from, id_to, len(sites))
        else:
            # Use interleaved queue: priority sites mixed fairly with normal sites
            sites = get_active_sites_interleaved()
            priority_count = sum(1 for s in sites if s.get("is_priority"))
            log.info("Scraping all active sites → %d found (%d priority)",
                     len(sites), priority_count)

        if not sites:
            log.warning("No active sites to scrape.")
            return 0

        total_articles = 0
        total_sites    = len(sites)
        completed      = 0
        failed_sites   = 0
        run_started    = datetime.now()

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_site = {
                executor.submit(self.scrape_single_site, site, latest_n): site
                for site in sites
            }

            for future in as_completed(future_to_site):
                site = future_to_site[future]
                completed += 1
                try:
                    count = future.result()
                    total_articles += count
                    if count == 0:
                        failed_sites += 1
                    log.info(
                        "✓ [%d/%d] %s — %d articles  (total: %d)",
                        completed, total_sites, site["name"], count, total_articles,
                    )
                except Exception as e:
                    failed_sites += 1
                    log.error("Thread crash on %s: %s", site["name"], e)
                    traceback.print_exc()

        run_ended = datetime.now()
        duration  = (run_ended - run_started).total_seconds()

        save_scrape_run(
            sites_attempted=total_sites,
            sites_failed=failed_sites,
            articles_saved=total_articles,
            duration_seconds=int(duration),
            id_from=id_from,
            id_to=id_to,
        )

        log.info(
            "Run complete — %d articles from %d sites in %.1fs  (%d sites with 0 articles)",
            total_articles, total_sites, duration, failed_sites,
        )
        return total_articles
