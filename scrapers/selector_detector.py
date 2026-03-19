"""
selector_detector.py
--------------------
Heuristic-based CSS selector auto-detection for news sites.

Detects:
  - article_selector  : CSS selector to find article links on the homepage
  - title_selector    : CSS selector for the article title
  - content_selector  : CSS selector for the article body

Detection order:
  1. WordPress fingerprint  (most Nepali news sites run WP)
  2. Known CMS / framework patterns
  3. Generic scoring heuristics on live page HTML
"""

import re
import requests
import certifi
from bs4 import BeautifulSoup
from urllib.parse import urljoin

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
FETCH_TIMEOUT = 15

# ---------------------------------------------------------------------------
# 1. Ordered candidate lists  (tried top-to-bottom, first match wins)
# ---------------------------------------------------------------------------

ARTICLE_SELECTOR_CANDIDATES = [
    # WordPress standard
    ".post-title a", "h2.entry-title a", "h3.entry-title a",
    "article h2 a", "article h3 a", ".post h2 a", ".post h3 a",
    # Common Nepali/Asian news themes
    ".jeg_post_title a", ".td-module-title a", ".mvp-blog-story-text h2 a",
    ".jeg_block_content h3 a",
    ".news-title a", ".article-title a", ".story-title a",
    # Generic
    "h2 a[href]", "h3 a[href]",
    ".latest-news a", ".top-news a", ".breaking-news a",
    "a[href*='/news/']", "a[href*='/story/']", "a[href*='/article/']",
    "a[href*='/20']",  # year-based URLs (very common in Nepali sites)
]

TITLE_SELECTOR_CANDIDATES = [
    # WordPress / themes
    "h1.entry-title", "h1.post-title", "h2.entry-title",
    ".jeg_post_title", ".td-post-title h1", ".mvp-post-title",
    # Generic
    "h1.title", "h1.article-title", "h1.news-title",
    "h1.story-title", "h1.heading", "h2.heading",
    "h1",  # last resort
]

CONTENT_SELECTOR_CANDIDATES = [
    # WordPress standard
    "div.entry-content", "div.post-content", "div.the-content",
    # Known Nepali themes
    "div.ok18-single-post-content-wrap",    # OnlineKhabar
    "div.editor-box",                        # Ratopati
    "div.news-inner-wrapper",               # Ekantipur
    "div.jeg_post_content",                 # JNews theme (popular in Nepal)
    "div.td-post-content",                  # TDNews theme
    "div.mvp-content-main",                 # MVP theme
    # Generic
    "div.article-content", "div.article-body", "div.story-content",
    "div.news-content", "div.post-body", "div.content-area",
    "div.single-content", "div.main-content", "div.detail-content",
    "div[class*='content']", "div[class*='article']", "div[class*='story']",
    "article", "div.body",
]

# ---------------------------------------------------------------------------
# 2. WordPress-specific patterns  (engine_type = 'wordpress')
# ---------------------------------------------------------------------------

WP_SIGNATURES = [
    "/wp-content/", "/wp-includes/", "wp-json",
    "wp-embed.min.js", "generator.*wordpress",
]

WP_SELECTORS = {
    "article_selector": "h2.entry-title a",
    "title_selector":   "h1.entry-title",
    "content_selector": "div.entry-content",
}

# ---------------------------------------------------------------------------
# 3. Helper utilities
# ---------------------------------------------------------------------------

def _fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT, verify=certifi.where())
        r.encoding = "utf-8"
        return r.text
    except requests.exceptions.SSLError:
        try:
            r = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT, verify=False)
            r.encoding = "utf-8"
            return r.text
        except Exception:
            return None
    except Exception:
        return None


def _is_wordpress(html):
    """Return True if page HTML looks like WordPress."""
    low = html.lower()
    for sig in WP_SIGNATURES:
        if re.search(sig, low):
            return True
    return False


def _has_article_links(soup, selector, base_url, min_links=2):
    """Check if selector finds at least min_links plausible article hrefs."""
    found = 0
    for a in soup.select(selector):
        href = a.get("href", "")
        if not href or href.startswith("#") or href.startswith("javascript"):
            continue
        full = urljoin(base_url, href)
        # Must stay on same domain and look like a real page
        if base_url.split("//")[-1].split("/")[0] in full and len(full) > len(base_url) + 5:
            found += 1
            if found >= min_links:
                return True
    return False


def _has_text_content(soup, selector, min_chars=100):
    """Check if selector finds an element with enough text."""
    el = soup.select_one(selector)
    if not el:
        return False
    return len(el.get_text(strip=True)) >= min_chars


def _score_content_div(tag):
    """Score a div/article tag for likelihood of being the article body."""
    text = tag.get_text(strip=True)
    score = 0
    score += min(len(text) // 100, 20)          # text length (up to 20pts)
    score += len(tag.find_all("p")) * 2          # paragraph count
    score += len(tag.find_all("img"))            # images inside
    cls = " ".join(tag.get("class", []))
    for kw in ("content", "article", "story", "post", "body", "detail", "news", "text"):
        if kw in cls.lower():
            score += 5
    return score


# ---------------------------------------------------------------------------
# 4. Core detection logic
# ---------------------------------------------------------------------------

def detect_selectors(base_url):
    """
    Fetch the homepage + one sample article, then return a dict:
      {
        "article_selector": str | None,
        "title_selector":   str | None,
        "content_selector": str | None,
        "engine_type":      "wordpress" | "custom",
      }
    """
    result = {
        "article_selector": None,
        "title_selector":   None,
        "content_selector": None,
        "engine_type":      "custom",
    }

    # --- Fetch homepage ---
    homepage_html = _fetch(base_url)
    if not homepage_html:
        print(f"  [detector] Could not fetch homepage: {base_url}")
        return result

    home_soup = BeautifulSoup(homepage_html, "html.parser")

    # --- WordPress fast-path ---
    if _is_wordpress(homepage_html):
        result["engine_type"] = "wordpress"
        # Verify WP defaults actually work on this site
        wp_art = WP_SELECTORS["article_selector"]
        if _has_article_links(home_soup, wp_art, base_url):
            result["article_selector"] = wp_art
            result["title_selector"]   = WP_SELECTORS["title_selector"]
            result["content_selector"] = WP_SELECTORS["content_selector"]
            print(f"  [detector] WordPress detected, using WP defaults → {base_url}")
            # Verify content selector on a real article
            article_url = _pick_sample_article(home_soup, base_url, wp_art)
            if article_url:
                result = _verify_and_refine_article_selectors(result, article_url)
            return result
        # WP detected but default selectors don't match — fall through to heuristics

    # --- Article selector heuristic ---
    for sel in ARTICLE_SELECTOR_CANDIDATES:
        if _has_article_links(home_soup, sel, base_url):
            result["article_selector"] = sel
            print(f"  [detector] article_selector = '{sel}'")
            break

    if not result["article_selector"]:
        # Fallback: any <a> with year-like path
        result["article_selector"] = "a[href*='/20']"
        print(f"  [detector] article_selector fallback = 'a[href*=\"/20\"]'")

    # --- Fetch a sample article for title/content detection ---
    article_url = _pick_sample_article(home_soup, base_url, result["article_selector"])
    if not article_url:
        print(f"  [detector] No sample article found for {base_url}")
        # Use generic fallbacks
        result["title_selector"]   = "h1"
        result["content_selector"] = "div.entry-content"
        return result

    result = _verify_and_refine_article_selectors(result, article_url)
    return result


def _pick_sample_article(soup, base_url, article_selector):
    """Pick the first plausible article URL from the homepage."""
    for a in soup.select(article_selector):
        href = a.get("href", "")
        if not href or href.startswith("#"):
            continue
        full = urljoin(base_url, href)
        domain = base_url.split("//")[-1].split("/")[0]
        if domain in full and len(full) > len(base_url) + 5:
            return full
    return None


def _verify_and_refine_article_selectors(result, article_url):
    """Fetch a real article page and find working title/content selectors."""
    html = _fetch(article_url)
    if not html:
        result["title_selector"]   = result["title_selector"] or "h1"
        result["content_selector"] = result["content_selector"] or "div.entry-content"
        return result

    soup = BeautifulSoup(html, "html.parser")

    # --- Title ---
    if not result.get("title_selector"):
        for sel in TITLE_SELECTOR_CANDIDATES:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 10:
                result["title_selector"] = sel
                print(f"  [detector] title_selector = '{sel}'")
                break
        if not result["title_selector"]:
            result["title_selector"] = "h1"

    # --- Content ---
    if not result.get("content_selector"):
        # Try known candidates first
        for sel in CONTENT_SELECTOR_CANDIDATES:
            if _has_text_content(soup, sel, min_chars=150):
                result["content_selector"] = sel
                print(f"  [detector] content_selector = '{sel}'")
                break

        # If still nothing, score all divs and pick the best
        if not result["content_selector"]:
            best_tag = None
            best_score = 0
            for tag in soup.find_all(["div", "article", "section"]):
                score = _score_content_div(tag)
                if score > best_score:
                    best_score = score
                    best_tag = tag

            if best_tag and best_score > 10:
                # Build a selector from the tag's id or class
                tag_id = best_tag.get("id")
                tag_cls = best_tag.get("class", [])
                if tag_id:
                    result["content_selector"] = f"#{tag_id}"
                elif tag_cls:
                    result["content_selector"] = f"div.{tag_cls[0]}"
                else:
                    result["content_selector"] = best_tag.name
                print(f"  [detector] content_selector (scored) = '{result['content_selector']}'")
            else:
                result["content_selector"] = "div.entry-content"

    return result
