"""
populate_selectors.py
---------------------
One-time (or periodic) script that auto-detects and saves CSS selectors
for every active site that is still missing them in the database.

Usage:
    # Populate ALL sites missing selectors (runs in parallel)
    python populate_selectors.py

    # Limit to first N sites (useful for testing)
    python populate_selectors.py --limit 20

    # Use N worker threads (default: 10)
    python populate_selectors.py --workers 10

    # Force re-detect even if selectors already exist
    python populate_selectors.py --force
"""

import argparse
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

# Allow running from project root
sys.path.insert(0, ".")

from database import (
    get_sites_missing_selectors,
    get_active_sites,
    update_site_selectors,
    record_site_failure,
)
from scrapers.selector_detector import detect_selectors

DEFAULT_WORKERS = 10


def process_site(site):
    site_id   = site["id"]
    site_name = site["name"]
    base_url  = site["base_url"]

    print(f"\n→ [{site_id}] {site_name}  ({base_url})")

    try:
        detected = detect_selectors(base_url)

        art  = detected.get("article_selector")
        ttl  = detected.get("title_selector")
        cont = detected.get("content_selector")
        eng  = detected.get("engine_type", "custom")

        if art and ttl and cont:
            update_site_selectors(site_id, art, ttl, cont, eng)
            print(f"  ✓ Saved  engine={eng}  art='{art}'  title='{ttl}'  content='{cont}'")
            return "ok"
        else:
            print(f"  ✗ Partial detection — skipped DB write  {detected}")
            return "partial"

    except Exception as e:
        err = str(e)
        print(f"  ✗ Error: {err}")
        traceback.print_exc()
        record_site_failure(site_id, f"[selector_detect] {err}")
        return "error"


def main():
    parser = argparse.ArgumentParser(description="Auto-populate CSS selectors for news sites")
    parser.add_argument("--limit",   type=int, default=None, help="Process only first N sites")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Parallel threads")
    parser.add_argument("--force",   action="store_true", help="Re-detect even if selectors exist")
    args = parser.parse_args()

    if args.force:
        sites = get_active_sites()
        print(f"Force mode: processing all {len(sites)} active sites")
    else:
        sites = get_sites_missing_selectors(limit=args.limit)
        print(f"Sites missing selectors: {len(sites)}")

    if args.limit and not args.force:
        sites = sites[:args.limit]

    if not sites:
        print("Nothing to do — all sites already have selectors.")
        return

    stats = {"ok": 0, "partial": 0, "error": 0}

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_site = {executor.submit(process_site, s): s for s in sites}
        for future in as_completed(future_to_site):
            site = future_to_site[future]
            try:
                status = future.result()
                stats[status] = stats.get(status, 0) + 1
            except Exception as e:
                print(f"  Thread crash on {site['name']}: {e}")
                stats["error"] += 1

    print(f"\n{'='*50}")
    print(f"Done — ✓ {stats['ok']} saved  |  ~ {stats['partial']} partial  |  ✗ {stats['error']} errors")


if __name__ == "__main__":
    main()
