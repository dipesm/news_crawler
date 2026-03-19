# =============================================================================
# database.py
# =============================================================================

import mysql.connector
from datetime import datetime
from config import DB_CONFIG, AUTO_DISABLE_AFTER_FAILURES
from logger import get_logger
from utils.helpers import nepal_now, to_nepal_time

log = get_logger(__name__)


def get_connection():
    """
    Create a MySQL connection with utf8mb4 charset set via SQL.
    We avoid passing charset= in DB_CONFIG because mysql-connector-python
    misinterprets 'utf8mb4' as a Python codec name and raises:
      "unknown encoding: utf8mb4"
    """
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci")
    cursor.close()
    return conn


# -----------------------------------------------------------------------------
# FETCH ACTIVE SITES
# -----------------------------------------------------------------------------
def get_active_sites():
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM news_sites WHERE active=1 ORDER BY id")
        return cursor.fetchall()
    finally:
        conn.close()


def get_active_sites_by_range(id_from, id_to):
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM news_sites WHERE active=1 AND id BETWEEN %s AND %s ORDER BY id",
            (id_from, id_to)
        )
        return cursor.fetchall()
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# PRIORITY SITES
# -----------------------------------------------------------------------------
def get_priority_sites():
    """Return all priority sites regardless of failure count or active status."""
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM news_sites
            WHERE is_priority = 1
            ORDER BY id
        """)
        return cursor.fetchall()
    finally:
        conn.close()


def get_active_sites_interleaved():
    """
    Return active sites with priority sites interleaved fairly.
    Priority sites appear every PRIORITY_INTERLEAVE positions in the queue.
    Priority sites are always included even if active=0.
    """
    from config import PRIORITY_INTERLEAVE
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)

        # Priority sites (always included)
        cursor.execute("SELECT * FROM news_sites WHERE is_priority=1 ORDER BY id")
        priority = cursor.fetchall()

        # Normal active sites (exclude priority ones to avoid duplicates)
        cursor.execute("""
            SELECT * FROM news_sites
            WHERE active=1 AND is_priority=0
            ORDER BY id
        """)
        normal = cursor.fetchall()

        # Interleave: insert 1 priority site every PRIORITY_INTERLEAVE normal sites
        result = []
        p_idx  = 0
        for i, site in enumerate(normal):
            if p_idx < len(priority) and i % PRIORITY_INTERLEAVE == 0:
                result.append(priority[p_idx])
                p_idx += 1
            result.append(site)

        # Append any remaining priority sites not yet inserted
        result.extend(priority[p_idx:])
        return result
    finally:
        conn.close()


def set_site_priority(site_id, is_priority: bool):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE news_sites SET is_priority=%s WHERE id=%s",
            (1 if is_priority else 0, site_id)
        )
        conn.commit()
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# READ / UNREAD MANAGEMENT
# -----------------------------------------------------------------------------
def mark_article_read(article_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE news_articles SET is_read=1 WHERE id=%s", (article_id,)
        )
        conn.commit()
    finally:
        conn.close()


def mark_article_unread(article_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE news_articles SET is_read=0 WHERE id=%s", (article_id,)
        )
        conn.commit()
    finally:
        conn.close()


def mark_all_read(date=None):
    """Mark all articles as read. Optionally filter by scraped date."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if date:
            cursor.execute("""
                UPDATE news_articles SET is_read=1
                WHERE scraped_at BETWEEN %s AND %s
            """, (f"{date} 00:00:00", f"{date} 23:59:59"))
        else:
            cursor.execute("UPDATE news_articles SET is_read=1")
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_unread_count(date=None):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if date:
            cursor.execute("""
                SELECT COUNT(*) FROM news_articles
                WHERE is_read=0
                AND scraped_at BETWEEN %s AND %s
            """, (f"{date} 00:00:00", f"{date} 23:59:59"))
        else:
            cursor.execute("SELECT COUNT(*) FROM news_articles WHERE is_read=0")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_sites_missing_selectors(limit=None):
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT * FROM news_sites
            WHERE active = 1
              AND (
                  article_selector IS NULL OR article_selector = ''
                  OR title_selector IS NULL OR title_selector = ''
                  OR content_selector IS NULL OR content_selector = ''
              )
            ORDER BY id
        """
        if limit:
            query += f" LIMIT {int(limit)}"
        cursor.execute(query)
        return cursor.fetchall()
    finally:
        conn.close()


def clear_site_selectors(site_id):
    """
    Clear all three selectors for a site so the next scrape run
    triggers auto-detection via selector_detector.py.
    Called automatically when SELECTOR_MISMATCH or NO_LINKS is detected.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE news_sites
            SET article_selector = NULL,
                title_selector   = NULL,
                content_selector = NULL
            WHERE id = %s
        """, (site_id,))
        conn.commit()
        log.info("Selectors cleared for site ID %d — will re-detect on next run", site_id)
    finally:
        conn.close()


def update_site_selectors(site_id, article_selector, title_selector,
                          content_selector, engine_type=None):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if engine_type:
            cursor.execute("""
                UPDATE news_sites
                SET article_selector = %s,
                    title_selector   = %s,
                    content_selector = %s,
                    engine_type      = %s
                WHERE id = %s
            """, (article_selector, title_selector, content_selector, engine_type, site_id))
        else:
            cursor.execute("""
                UPDATE news_sites
                SET article_selector = %s,
                    title_selector   = %s,
                    content_selector = %s
                WHERE id = %s
            """, (article_selector, title_selector, content_selector, site_id))
        conn.commit()
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# DUPLICATE CHECK
# -----------------------------------------------------------------------------
def get_existing_links(links):
    """Return the subset of links already saved in the DB — avoids re-scraping."""
    if not links:
        return set()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        placeholders = ",".join(["%s"] * len(links))
        cursor.execute(
            f"SELECT link FROM news_articles WHERE link IN ({placeholders})",
            list(links)
        )
        return {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# SAVE ARTICLES
# Requires these columns in news_articles (run migration.sql if not present):
#   content_hash  CHAR(64)
#   language      VARCHAR(5)
# -----------------------------------------------------------------------------
def save_articles(articles):
    if not articles:
        return 0

    conn   = get_connection()
    cursor = conn.cursor()

    query = """
    INSERT INTO news_articles
    (title, link, content, category, published_date,
     date_source, date_confidence,
     image_url, local_image_path, source,
     is_political, is_election_related, is_toxic,
     is_read, content_hash, scraped_at)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE
        title           = VALUES(title),
        content         = VALUES(content),
        content_hash    = VALUES(content_hash),
        scraped_at      = VALUES(scraped_at)
        -- NOTE: is_read is NOT updated on duplicate so read state is preserved
    """

    data = []
    for article in articles:
        # published_date may be a DateResult, datetime, or None
        pub = article.get("published_date")
        if hasattr(pub, "dt"):                   # DateResult object
            pub_dt     = pub.dt
            date_src   = pub.source
            date_conf  = pub.confidence
        elif isinstance(pub, datetime):
            pub_dt    = pub
            date_src  = "legacy"
            date_conf = "medium"
        else:
            pub_dt    = None
            date_src  = "none"
            date_conf = "none"

        # ── AD-only guard ─────────────────────────────────────────────────
        # pub_dt must be a valid AD year (2010–current year).
        # If year > 2040 it is a BS date that was not converted — discard it.
        # If year is in the future it slipped past validation — discard it.
        if pub_dt is not None:
            from datetime import date as date_type
            pub_year = pub_dt.year if isinstance(pub_dt, datetime) else pub_dt.year
            today_year = nepal_now().year
            if pub_year > today_year:
                log.warning(
                    "Discarding future/BS published_date %s (year=%d) for: %s",
                    pub_dt, pub_year, article.get("link", "?")
                )
                pub_dt    = None
                date_src  = "discarded_invalid"
                date_conf = "none"
            elif pub_year < 2010:
                log.warning(
                    "Discarding pre-2010 published_date %s for: %s",
                    pub_dt, article.get("link", "?")
                )
                pub_dt    = None
                date_src  = "discarded_invalid"
                date_conf = "none"

        row = (
            article.get("title"),
            article.get("link"),
            article.get("content"),
            article.get("category"),
            pub_dt,
            date_src,
            date_conf,
            article.get("image_url"),
            article.get("local_image_path"),
            article.get("source"),
            article.get("is_political",        "No"),
            article.get("is_election_related",  "No"),
            article.get("is_toxic",             "No"),
            0,                                   # is_read = 0 (unread) by default
            article.get("content_hash"),
            nepal_now(),             # scraped_at in Nepal Standard Time
        )
        data.append(row)

    try:
        cursor.executemany(query, data)
        conn.commit()
        saved = cursor.rowcount
        log.info("DB: Inserted/Updated %d articles", saved)
        return saved
    except mysql.connector.Error as e:
        log.error("MySQL Insert Error: %s", e)
        return 0
    finally:
        cursor.close()
        conn.close()


# -----------------------------------------------------------------------------
# SCRAPE RUN STATS  (requires scrape_runs table — see migration.sql)
# -----------------------------------------------------------------------------
def save_scrape_run(sites_attempted, sites_failed, articles_saved,
                    duration_seconds, id_from=None, id_to=None):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO scrape_runs
            (started_at, sites_attempted, sites_failed,
             articles_saved, duration_seconds, id_from, id_to)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (nepal_now(), sites_attempted, sites_failed,
              articles_saved, duration_seconds, id_from, id_to))
        conn.commit()
        log.info(
            "Run stats saved — %d sites, %d failed, %d articles, %ds",
            sites_attempted, sites_failed, articles_saved, duration_seconds,
        )
    except mysql.connector.Error as e:
        log.warning("Could not save scrape run stats: %s", e)
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# FAILURE & SUCCESS TRACKING
#
# failure_count   = CONSECUTIVE failures since last success
#                   Resets to 0 on success. Used to auto-disable dead sites.
#
# success_count   = total lifetime successes (never resets)
#
# stability_score = success_count / (success_count + total_failures)
#                   Range: 0.0 (always fails) → 1.0 (always succeeds)
#                   Reflects long-term reliability of the site.
# -----------------------------------------------------------------------------
def record_site_failure(site_id, error_message, force_disable=False):
    """
    Records a scrape failure:
    - Increments consecutive failure_count
    - Saves last_error message
    - Recalculates stability_score
    - Auto-disables if consecutive failures >= AUTO_DISABLE_AFTER_FAILURES
    - force_disable=True disables immediately (used for dead domains)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE news_sites
            SET failure_count   = failure_count + 1,
                last_error      = %s,
                stability_score = CASE
                    WHEN (success_count + failure_count + 1) > 0
                    THEN success_count / (success_count + failure_count + 1)
                    ELSE 0
                END
            WHERE id = %s
        """, (str(error_message)[:1000], site_id))
        conn.commit()

        cursor.execute(
            "SELECT failure_count, is_priority FROM news_sites WHERE id=%s", (site_id,)
        )
        row        = cursor.fetchone()
        consecutive = row[0] if row else 0
        is_priority = row[1] if row else 0

        if force_disable:
            if is_priority:
                log.warning("Site ID %d is dead domain but PRIORITY — kept active.", site_id)
            else:
                cursor.execute("UPDATE news_sites SET active=0 WHERE id=%s", (site_id,))
                conn.commit()
                log.warning("Site ID %d force-disabled (dead domain).", site_id)
            return

        if consecutive >= AUTO_DISABLE_AFTER_FAILURES:
            if is_priority:
                # Never disable priority sites — just log the warning
                log.warning(
                    "Site ID %d has %d consecutive failures but is PRIORITY — kept active.",
                    site_id, consecutive
                )
            else:
                cursor.execute("UPDATE news_sites SET active=0 WHERE id=%s", (site_id,))
                conn.commit()
                log.warning(
                    "Site ID %d auto-disabled after %d consecutive failures.",
                    site_id, consecutive
                )

    finally:
        conn.close()


def record_site_success(site_id):
    """
    Records a successful scrape (articles found and saved):
    - Increments lifetime success_count
    - Resets consecutive failure_count to 0
    - Clears last_error
    - Recalculates stability_score
    - Updates last_scraped timestamp
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE news_sites
            SET success_count   = success_count + 1,
                failure_count   = 0,
                last_error      = NULL,
                last_scraped    = %s,
                stability_score = CASE
                    WHEN (success_count + failure_count + 1) > 0
                    THEN (success_count + 1) / (success_count + failure_count + 1)
                    ELSE 1
                END
            WHERE id = %s
        """, (datetime.now(), site_id))
        conn.commit()
    finally:
        conn.close()
