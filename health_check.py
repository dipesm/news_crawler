"""
health_check.py — Test selectors on any site without saving to DB.

Usage:
    python health_check.py --url https://onlinekhabar.com
    python health_check.py --id 5
    python health_check.py --all          # check all active sites, print report
    python health_check.py --failing      # check only sites with failures
"""

import argparse
import sys
from datetime import datetime
import requests
import certifi
from bs4 import BeautifulSoup
from urllib.parse import urljoin

sys.path.insert(0, ".")
from database import get_active_sites, get_connection
from scrapers.selector_detector import detect_selectors
from logger import get_logger

log = get_logger("health_check")


def fetch(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=8, verify=certifi.where())
        r.encoding = "utf-8"
        return r.text
    except Exception:
        try:
            r = requests.get(url, headers=headers, timeout=8, verify=False)
            r.encoding = "utf-8"
            return r.text
        except Exception as e:
            return None


def check_site(site):
    url      = site["base_url"]
    name     = site["name"]
    art_sel  = site.get("article_selector")
    ttl_sel  = site.get("title_selector")
    cnt_sel  = site.get("content_selector")

    result = {
        "id":        site["id"],
        "name":      name,
        "url":       url,
        "reachable": False,
        "article_links_found": 0,
        "title_ok":  False,
        "content_ok": False,
        "selectors_detected": False,
        "issues":    [],
    }

    # 1. Reachability
    html = fetch(url)
    if not html:
        result["issues"].append("Site unreachable")
        return result
    result["reachable"] = True

    # 2. Auto-detect selectors if missing
    if not art_sel or not ttl_sel or not cnt_sel:
        log.info("No selectors stored — running detector for %s", url)
        detected = detect_selectors(url)
        art_sel  = art_sel  or detected.get("article_selector")
        ttl_sel  = ttl_sel  or detected.get("title_selector")
        cnt_sel  = cnt_sel  or detected.get("content_selector")
        result["selectors_detected"] = True

    # 3. Article links
    soup  = BeautifulSoup(html, "html.parser")
    links = []
    if art_sel:
        for a in soup.select(art_sel):
            href = a.get("href")
            if href:
                links.append(urljoin(url, href))
    result["article_links_found"] = len(links)
    if not links:
        result["issues"].append(f"No article links found with selector '{art_sel}'")

    # 4. Test title + content on first article
    if links:
        article_html = fetch(links[0])
        if article_html:
            asoup = BeautifulSoup(article_html, "html.parser")
            if ttl_sel and asoup.select_one(ttl_sel):
                result["title_ok"] = True
            else:
                result["issues"].append(f"Title selector '{ttl_sel}' not found on article page")

            if cnt_sel:
                el = asoup.select_one(cnt_sel)
                if el and len(el.get_text(strip=True)) > 100:
                    result["content_ok"] = True
                else:
                    result["issues"].append(f"Content selector '{cnt_sel}' empty or too short")
        else:
            result["issues"].append("Could not fetch sample article")

    return result


def print_result(r):
    status = "✓ OK" if not r["issues"] else "✗ ISSUES"
    print(f"\n[{r['id']}] {r['name']} ({r['url']})")
    print(f"  Status      : {status}")
    print(f"  Reachable   : {r['reachable']}")
    print(f"  Links found : {r['article_links_found']}")
    print(f"  Title OK    : {r['title_ok']}")
    print(f"  Content OK  : {r['content_ok']}")
    if r["selectors_detected"]:
        print(f"  Note        : Selectors were auto-detected (not saved)")
    if r["issues"]:
        for issue in r["issues"]:
            print(f"  ⚠ {issue}")


def get_site_by_id(site_id):
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM news_sites WHERE id = %s", (site_id,))
        return cursor.fetchone()
    finally:
        conn.close()


def get_failing_sites():
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM news_sites WHERE active=1 AND failure_count > 0 ORDER BY failure_count DESC"
        )
        return cursor.fetchall()
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Health check for news sites")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url",     type=str, help="Test a specific URL")
    group.add_argument("--id",      type=int, help="Test site by DB id")
    group.add_argument("--all",     action="store_true", help="Check all active sites")
    group.add_argument("--failing", action="store_true", help="Check sites with failures")
    args = parser.parse_args()

    if args.url:
        site = {"id": 0, "name": args.url, "base_url": args.url,
                "article_selector": None, "title_selector": None, "content_selector": None}
        print_result(check_site(site))

    elif args.id:
        site = get_site_by_id(args.id)
        if not site:
            print(f"No site found with id={args.id}")
            sys.exit(1)
        print_result(check_site(site))

    elif args.all or args.failing:
        sites   = get_failing_sites() if args.failing else get_active_sites()
        ok      = 0
        issues  = 0
        print(f"\nChecking {len(sites)} sites...\n{'='*60}")
        for site in sites:
            r = check_site(site)
            print_result(r)
            if r["issues"]:
                issues += 1
            else:
                ok += 1
        print(f"\n{'='*60}")
        print(f"Summary: {ok} OK  |  {issues} with issues  |  {len(sites)} total")
        print(f"Report generated: {datetime.now():%Y-%m-%d %H:%M:%S}")


if __name__ == "__main__":
    main()
