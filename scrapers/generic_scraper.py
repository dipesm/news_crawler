# =============================================================================
# generic_scraper.py
# =============================================================================

import re
import hashlib
import requests
import certifi
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timedelta

from config import FETCH_TIMEOUT, MAX_ARTICLE_AGE_DAYS
from logger import get_logger
from rate_limiter import wait_if_needed
from robots_checker import is_allowed
from keyword_filter import url_passes, content_passes
from utils.helpers import safe_text, download_image, classify_article, detect_category, extract_publish_date, nepal_now, to_nepal_time
from scrapers.selector_detector import detect_selectors
from database import update_site_selectors, get_existing_links

log = get_logger(__name__)


class DeadSiteError(Exception):
    """Raised when a site's domain cannot be resolved (dead/expired domain).
    Signals the scraper manager to skip retries entirely."""
    pass


class _DateRejected(Exception):
    """Internal: article rejected by date filter."""
    pass


class _KeywordRejected(Exception):
    """Internal: article rejected by keyword filter."""
    pass


class GenericScraper:
    def __init__(self, site, force_redetect=False):
        self.site             = site
        self.base_url         = site["base_url"]
        self.force_redetect   = force_redetect
        # Load selectors from site dict (may be None if cleared)
        self.article_selector = site.get("article_selector") or None
        self.title_selector   = site.get("title_selector")   or None
        self.content_selector = site.get("content_selector") or None

    def clear_selectors(self):
        """Wipe in-memory selectors so _ensure_selectors re-detects them."""
        self.article_selector = None
        self.title_selector   = None
        self.content_selector = None
        self.force_redetect   = True

    # ------------------------------------------------------------------
    # Selector bootstrap — auto-detects and saves if missing from DB
    # ------------------------------------------------------------------
    def _ensure_selectors(self):
        # Skip if all three are present AND not forced to re-detect
        if (self.article_selector and self.title_selector
                and self.content_selector and not self.force_redetect):
            return

        log.info("Auto-detecting selectors for %s%s",
                 self.base_url, " (forced re-detect)" if self.force_redetect else "")
        detected = detect_selectors(self.base_url)

        self.article_selector = detected.get("article_selector") or "a[href*='/20']"
        self.title_selector   = detected.get("title_selector")   or "h1"
        self.content_selector = detected.get("content_selector") or "div.entry-content"
        engine = detected.get("engine_type", self.site.get("engine_type", "custom"))
        self.force_redetect   = False  # reset flag

        try:
            update_site_selectors(
                self.site["id"],
                self.article_selector,
                self.title_selector,
                self.content_selector,
                engine,
            )
            log.info(
                "Selectors saved — art='%s'  title='%s'  content='%s'",
                self.article_selector, self.title_selector, self.content_selector,
            )
        except Exception as e:
            log.warning("DB write failed for selectors (continuing): %s", e)

    # ------------------------------------------------------------------
    # HTTP — rate-limited, robots-aware, SSL-tolerant, fast timeout
    # ------------------------------------------------------------------
    def fetch_page(self, url):
        if not is_allowed(url):
            log.info("Skipped (robots.txt): %s", url)
            return None

        wait_if_needed(url)

        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            r = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT, verify=certifi.where())
            r.encoding = "utf-8"
            return r.text

        except requests.exceptions.SSLError:
            try:
                r = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT, verify=False)
                r.encoding = "utf-8"
                return r.text
            except Exception as e:
                log.warning("SSL retry failed for %s: %s", url, e)
                return None

        except requests.exceptions.ConnectionError as e:
            err = str(e)
            if "NameResolutionError" in err or "getaddrinfo failed" in err or "Failed to resolve" in err:
                # Dead domain — no point retrying, raise so manager skips retries
                raise DeadSiteError(f"Domain does not exist: {url}")
            log.warning("Connection error for %s: %s", url, err)
            return None

        except requests.exceptions.Timeout:
            log.warning("Timeout fetching %s", url)
            return None

        except Exception as e:
            log.warning("Fetch failed for %s: %s", url, e)
            return None

    # ------------------------------------------------------------------
    # URL-level date pre-filter (no HTTP cost)
    # Handles: /2026/03/15/story  /2026/03/story  /2026/story
    # Compares DATE only (not datetime) so time-of-day doesn't cause
    # same-day articles to be rejected.
    # ------------------------------------------------------------------
    def _url_is_too_old(self, url):
        """
        Fast URL-only pre-filter. Handles all slug formats.
        Returns True if URL date is too old OR in the future.
        """
        from datetime import date as date_type
        cutoff = (nepal_now() - timedelta(days=MAX_ARTICLE_AGE_DAYS)).date()
        today  = nepal_now().date()

        # Try to extract full date (returns None if future or unparseable)
        d = self._date_from_url(url)
        if d is not None:
            return d < cutoff  # future already excluded by _date_from_url

        # Check if URL contains a date that _date_from_url rejected as future
        # e.g. /posts/2026-05-01-event
        m_slug = re.search(r"[/-](20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(?=[^0-9]|$)", url)
        if m_slug:
            try:
                d_raw = date_type(int(m_slug.group(1)), int(m_slug.group(2)), int(m_slug.group(3)))
                if d_raw > today:
                    log.info("Rejected FUTURE URL date: %s in %s", d_raw, url)
                    return True   # future date in URL — reject
                if d_raw < cutoff:
                    return True   # old date — reject
            except ValueError:
                pass

        # Year-only fallback
        m = re.search(r"[/-](20\d{2})[/-]", url)
        if m:
            y = int(m.group(1))
            if y < cutoff.year:
                return True
            if y > today.year:
                log.info("Rejected FUTURE year %d in URL: %s", y, url)
                return True

        return False  # can't determine — let content check decide

    # ------------------------------------------------------------------
    # Article-level date filter — handles DateResult, datetime, date, None
    # Compares DATE only so time-of-day doesn't cause same-day rejections.
    # ------------------------------------------------------------------
    def _is_too_old(self, val):
        """
        Returns True if the article should be rejected:
        - Date is older than MAX_ARTICLE_AGE_DAYS
        - Date is in the future (impossible publish date)
        """
        from utils.helpers import DateResult
        from datetime import date as date_type

        dt = val.dt if isinstance(val, DateResult) else val
        if dt is None:
            return False  # no date — assumed_today fallback handles it

        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.split("+")[0].strip())
            except Exception:
                return False

        if hasattr(dt, "tzinfo") and dt.tzinfo:
            dt = dt.replace(tzinfo=None)

        d      = dt.date() if isinstance(dt, datetime) else dt
        today  = nepal_now().date()
        cutoff = (nepal_now() - timedelta(days=MAX_ARTICLE_AGE_DAYS)).date()

        # Reject future dates — a published article cannot be dated tomorrow
        if d > today:
            log.info("Rejected FUTURE article date: %s (today: %s, source: %s)",
                     d, today, getattr(val, 'source', '?'))
            return True

        # Reject old dates
        if d < cutoff:
            return True

        return False

    # ------------------------------------------------------------------
    # Content hash — detects unchanged articles on re-scrape
    # ------------------------------------------------------------------
    @staticmethod
    def _content_hash(title, content):
        return hashlib.sha256(f"{title}||{content}".encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Language detection — Devanagari character ratio
    # ------------------------------------------------------------------
    @staticmethod
    def _detect_language(text):
        """
        Detect language by Devanagari character ratio.
        Most Nepali articles are >40% Devanagari.
        Mixed content or English-dominant articles fall below 30%.
        """
        if not text:
            return "ne"  # default for Nepal news sites
        devanagari = sum(1 for c in text if "\u0900" <= c <= "\u097F")
        ratio = devanagari / len(text)
        if ratio > 0.35:
            return "ne"
        elif ratio > 0.10:
            return "ne_en"  # mixed Nepali/English
        else:
            return "en"

    # ------------------------------------------------------------------
    # Parse article links from homepage HTML
    # ------------------------------------------------------------------
    def parse_article_links(self, html):
        soup  = BeautifulSoup(html, "html.parser")
        links = set()
        for a in soup.select(self.article_selector):
            href = a.get("href")
            if href:
                links.add(urljoin(self.base_url, href))
        return links

    # ------------------------------------------------------------------
    # Extract date from URL slug as fallback
    # e.g. /nepal-myanmar-sign-mou/ → None (no date)
    #      /2026/03/15/story/       → date(2026, 3, 15)
    # ------------------------------------------------------------------
    @staticmethod
    def _date_from_url(url):
        """
        Extract a date from URL patterns. Supports:
          /2026/03/15/story        → 2026-03-15
          /2026/03/15-02-34-53     → 2026-03-15  (datetime slug)
          /posts/2026-03-15-story  → 2026-03-15  (date-in-slug)
          /2026/03/                → 2026-03-01  (month only)
        Validates: year must be 2010–current_year, must not be future.
        """
        from datetime import date as date_type
        today = date_type.today()

        # Pattern 1: /YYYY/MM/DD/ (classic WordPress format)
        m = re.search(r"/(\d{4})/(\d{2})/(\d{2})[/-]", url)
        if m:
            try:
                d = date_type(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if 2010 <= d.year <= today.year and d <= today:
                    return d
            except ValueError:
                pass

        # Pattern 2: YYYY-MM-DD anywhere in URL slug (e.g. ictkhabar.com)
        # Matches: /posts/2026-03-15-02-34-53 → 2026-03-15
        m = re.search(r"[/-](20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(?=[^0-9]|$)", url)
        if m:
            try:
                d = date_type(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if 2010 <= d.year <= today.year and d <= today:
                    return d
            except ValueError:
                pass

        # Pattern 3: /YYYY/MM/ only (conservative — use day 1)
        m = re.search(r"/(\d{4})/(\d{2})/", url)
        if m:
            try:
                d = date_type(int(m.group(1)), int(m.group(2)), 1)
                if 2010 <= d.year <= today.year and d <= today:
                    return d
            except ValueError:
                pass

        return None

    # ------------------------------------------------------------------
    # Fetch and parse a single article page
    # ------------------------------------------------------------------
    def parse_article(self, url):
        html = self.fetch_page(url)
        if not html:
            return None

        soup        = BeautifulSoup(html, "html.parser")
        title_tag   = soup.select_one(self.title_selector)
        content_div = soup.select_one(self.content_selector)

        if not title_tag or not content_div:
            return None

        title   = safe_text(title_tag.get_text(strip=True))
        content = safe_text(
            " ".join(p.get_text(strip=True) for p in content_div.find_all("p"))
        )

        if len(content) < 50:
            return None

        # --- Date resolution (4 levels) ---
        from utils.helpers import DateResult, _parse_bs_date, _parse_text_date,                                   _validate_date, _ensure_ad_date

        # Level 1: extract_publish_date — JSON-LD, meta, time tags, CSS,
        #          BS calendar conversion, relative dates, text scan, ISO regex.
        # Convert extracted date to Nepal time if it has timezone info
        raw_result  = extract_publish_date(soup)
        if raw_result and raw_result.dt and hasattr(raw_result.dt, 'tzinfo') and raw_result.dt.tzinfo:
            raw_result.dt = to_nepal_time(raw_result.dt)
        date_result = _ensure_ad_date(raw_result, url)

        # Level 2: URL slug date (e.g. /2026/03/17/ or /2026-03-17-slug)
        if not date_result:
            url_date = self._date_from_url(url)
            if url_date:
                date_result = DateResult(url_date, "url", "medium")
                log.debug("Date from URL: %s", url_date)

        # Level 3: Scan article content text directly.
        # Catches sites like liveprades.com / gatishildaily.com that put
        # the date only in visible paragraph text, not in any meta tag.
        if not date_result:
            dt, conf, _ = _parse_bs_date(content[:2000])
            if dt:
                date_result = _ensure_ad_date(
                    DateResult(dt, "bs_content_scan", conf), url)
                if date_result:
                    log.debug("Date from content BS scan: %s", dt.date())
            if not date_result:
                dt, conf, _ = _parse_text_date(content[:2000])
                if dt:
                    date_result = _ensure_ad_date(
                        DateResult(dt, "text_content_scan", conf), url)
                    if date_result:
                        log.debug("Date from content text scan: %s", dt.date())

        # Level 4: no date found anywhere — assume today.
        # Only fires for sites that genuinely publish no dates (rare).
        if not date_result:
            from datetime import date as date_type
            date_result = DateResult(
                datetime.combine(nepal_now().date(), datetime.min.time()),
                "assumed_today", "low"
            )
            log.info("No date found — assuming today: %s", url)

        # Final filter — reject old AND future dates
        if self._is_too_old(date_result):
            log.info("Rejected article (date=%s src=%s): %s",
                     date_result.dt.date() if date_result.dt else None,
                     date_result.source, url)
            raise _DateRejected()

        published_date = date_result  # stored as AD datetime in DB

        # Keyword filter: skip articles not matching keywords (if enabled)
        if not content_passes(title, content):
            log.debug("Keyword mismatch — skipped: %s", title[:80])
            raise _KeywordRejected()

        image_tag = content_div.find("img")
        image_url = (
            image_tag.get("src") or image_tag.get("data-src") or image_tag.get("data-original")
            if image_tag else None
        )
        local_path     = download_image(image_url)
        is_political, is_election, category = classify_article(title, content)
        content_hash   = self._content_hash(title, content)
        language       = self._detect_language(content)

        return {
            "title":               title,
            "link":                url,
            "content":             content,
            "category":            category,
            "published_date":      published_date,
            "image_url":           image_url,
            "local_image_path":    local_path,
            "source":              self.site["name"],
            "is_political":        is_political,
            "is_election_related": is_election,
            "is_toxic":            "No",
            "content_hash":        content_hash,
            "language":            language,
        }

    # ------------------------------------------------------------------
    # Main entry point
    # Returns (articles, zero_reason) where zero_reason explains why
    # 0 articles were returned so the manager can handle each case
    # differently — no false failure penalties for healthy sites.
    # ------------------------------------------------------------------
    def scrape(self, latest_n=20):
        try:
            # Step 0: ensure selectors exist (auto-detect + save if missing)
            self._ensure_selectors()

            # Step 1: fetch homepage and collect article links
            html = self.fetch_page(self.base_url)
            if not html:
                raise Exception("Homepage fetch failed")

            raw_links = list(self.parse_article_links(html))[:latest_n]
            if not raw_links:
                return [], "NO_LINKS"   # selector not matching anything

            total_raw = len(raw_links)

            # Step 2: URL date pre-filter (no HTTP)
            links = [l for l in raw_links if not self._url_is_too_old(l)]
            dropped_old_url = total_raw - len(links)

            # Step 3: URL keyword pre-filter (no HTTP)
            before_kw = len(links)
            links     = [l for l in links if url_passes(l)]
            dropped_kw = before_kw - len(links)

            if not links:
                reason = f"ALL_FILTERED_BEFORE_FETCH total={total_raw} old_url={dropped_old_url} kw={dropped_kw}"
                log.info("%s — %s", self.site["name"], reason)
                return [], reason

            # Step 4: duplicate check
            existing  = get_existing_links(set(links))
            new_links = [l for l in links if l not in existing]

            if not new_links:
                log.info("%s — all %d links already in DB (skipped cleanly)",
                         self.site["name"], len(links))
                return [], "ALL_DUPLICATE"   # healthy — not a failure

            log.info("%s — %d new / %d already in DB",
                     self.site["name"], len(new_links), len(existing))

            # Step 5: fetch + parse + filter
            skipped_date    = 0
            skipped_parse   = 0
            skipped_keyword = 0
            articles        = []

            for url in new_links:
                try:
                    article = self.parse_article(url)
                    if article:
                        articles.append(article)
                    else:
                        skipped_parse += 1
                except _DateRejected:
                    skipped_date += 1
                except _KeywordRejected:
                    skipped_keyword += 1

            # Build a detailed reason string for the manager to log/store
            parts = [f"scraped={len(articles)}"]
            if skipped_date:    parts.append(f"too_old={skipped_date}")
            if skipped_keyword: parts.append(f"kw_miss={skipped_keyword}")
            if skipped_parse:   parts.append(f"parse_fail={skipped_parse}")
            if dropped_old_url: parts.append(f"old_url={dropped_old_url}")

            summary = "  |  ".join(parts)
            log.info("%s — %s", self.site["name"], summary)

            if len(articles) == 0:
                # Determine the dominant reason for zero articles
                if skipped_date > 0 and skipped_parse == 0:
                    zero_reason = f"ALL_TOO_OLD {summary}"
                elif skipped_parse > 0 and skipped_date == 0:
                    zero_reason = f"SELECTOR_MISMATCH {summary}"
                elif skipped_keyword > 0:
                    zero_reason = f"ALL_KEYWORD_FILTERED {summary}"
                else:
                    zero_reason = f"UNKNOWN {summary}"
                return [], zero_reason

            return articles, None   # None = no zero_reason, success

        except DeadSiteError:
            raise   # let manager handle — no retry needed

        except Exception as e:
            log.error("[SCRAPE FAILED] %s → %s", self.site["name"], e)
            raise   # re-raise so manager records proper failure
