# 🗞️ News Scraper

A production-grade, multi-threaded news scraper for Nepali news websites. Automatically discovers CSS selectors, extracts articles, converts Bikram Sambat dates, categorises content, and stores everything in MySQL — with a full PHP dashboard for reading and managing scraped news.

---

## ✨ Features

- **Auto-detects CSS selectors** — no manual configuration per site; the selector detector fingerprints WordPress and common Nepali CMS patterns automatically
- **Multi-threaded** — scrapes up to 50 sites in parallel with configurable worker count
- **Smart date parsing** — 8-level date extraction pipeline (JSON-LD → meta tags → `<time>` → CSS → Bikram Sambat scan → relative dates → text → ISO regex), with future-time capping and BS→AD conversion using a verified anchor
- **Bikram Sambat support** — converts BS calendar dates to AD using a verified anchor point (`BS 2082/01/01 = AD 2025-04-14`), eliminating the 14-day error that accumulates in epoch-walk methods
- **Auto-category detection** — classifies articles into 12 categories (Politics, Economy, Sports, Technology, Health, Education, Entertainment, Environment, International, Crime, Business, General) with bilingual (Nepali + English) keyword matching
- **Language detection** — detects Nepali (`ne`), English (`en`), and mixed (`ne_en`) articles by Devanagari character ratio
- **Failure tracking** — auto-disables sites after N consecutive failures; priority sites are never disabled
- **Duplicate detection** — SHA-256 content hashing prevents re-saving unchanged articles
- **Rate limiting** — polite per-domain throttling to avoid IP bans
- **Robots.txt support** — optional compliance checking with TTL-based caching
- **Read/unread tracking** — articles are marked unread on scrape; the dashboard tracks reading state

---

## 📁 Project Structure

```
news-scraper/
├── main.py                    # Entry point — CLI with argparse
├── config.py                  # All settings in one place
├── scraper_manager.py         # Thread pool, retry logic, run stats
├── keyword_filter.py          # Optional keyword-based article filtering
├── rate_limiter.py            # Per-domain request throttling
├── robots_checker.py          # robots.txt compliance (optional)
├── health_check.py            # CLI tool to test selectors without saving
├── logger.py                  # Rotating file + console logger
├── database.py                # All MySQL queries (no ORM)
├── news.sql              	   # Initial schema additions (run once)
├── populate_selectors.py      # Bulk-seed selectors for known sites
├── scrapers/
│   ├── generic_scraper.py     # Core scraper used for all sites
│   └── selector_detector.py   # Heuristic CSS selector auto-detection
└── utils/
    └── helpers.py             # Date parsing, BS↔AD conversion, classification
```

---

## ⚙️ Requirements

- Python 3.9+
- MySQL 5.7+ / MariaDB 10.3+
- PHP 8.0+ (for the dashboard only)

### Python dependencies

```bash
pip install requests beautifulsoup4 mysql-connector-python certifi lxml
```

---

## 🚀 Setup

### 1. Clone and install

```bash
git clone https://github.com/yourname/news-scraper.git
cd news-scraper
pip install -r requirements.txt
```

### 2. Configure the database

Edit `config.py`:

```python
DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "yourpassword",
    "database": "ecn",
}
```

### 3. Run migrations

```bash
mysql -u root -p ecn < news.sql
```

### 4. Add news sites to the database

Insert sites into `ecn.news_sites`:

```sql
INSERT INTO ecn.news_sites (name, base_url, active) VALUES
  ('Online Khabar',  'https://www.onlinekhabar.com',  1),
  ('Ratopati',       'https://ratopati.com',           1),
  ('Setopati',       'https://www.setopati.com',       1),
  ('Ekantipur',      'https://ekantipur.com',          1);
```

CSS selectors are auto-detected on the first run. You can also pre-populate them:

```bash
python populate_selectors.py
```

### 5. Run the scraper

```bash
# Scrape all active sites
python main.py

# Scrape with custom settings
python main.py --workers 20 --latest 30 --days 2

# Scrape a specific range of site IDs
python main.py --from-id 1 --to-id 50
```

---

## ⚙️ Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `MAX_WORKERS` | `50` | Parallel threads |
| `MAX_RETRIES` | `2` | Retries per site before giving up |
| `FETCH_TIMEOUT` | `8` | HTTP timeout in seconds |
| `MAX_ARTICLE_AGE_DAYS` | `1` | Skip articles older than this |
| `MAX_ARTICLES_PER_SITE` | `20` | Max articles to process per site per run |
| `USE_KEYWORDS` | `False` | Enable keyword filtering |
| `RATE_LIMIT_CALLS` | `5` | Max requests per domain per window |
| `RATE_LIMIT_PERIOD` | `10` | Rate limit window in seconds |
| `AUTO_DISABLE_AFTER_FAILURES` | `3` | Disable site after N failures |
| `PRIORITY_INTERLEAVE` | `5` | 1 priority site per N normal sites in queue |
| `RESPECT_ROBOTS_TXT` | `False` | Honour robots.txt (most Nepali sites block all bots) |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_RETENTION_DAYS` | `14` | Days to keep log files |

### Keyword filtering

To collect only politically relevant articles, enable keyword mode:

```python
USE_KEYWORDS = True
```

Then customise `KEYWORDS` with Nepali and English terms. Set `KEYWORD_MATCH = "any"` (at least one keyword) or `"all"` (every keyword must match).

---

## 🔧 CLI Reference

### `main.py`

```
python main.py [options]

Options:
  --from-id INT    Start scraping from this site ID
  --to-id   INT    Stop scraping at this site ID
  --latest  INT    Max articles per site (default: 20)
  --workers INT    Override MAX_WORKERS
  --days    INT    Override MAX_ARTICLE_AGE_DAYS
```

### `health_check.py`

Test selectors and connectivity without saving anything to the database:

```bash
# Test a specific URL
python health_check.py --url https://onlinekhabar.com

# Test a site by its DB id
python health_check.py --id 5

# Check all active sites
python health_check.py --all

# Check only sites with recorded failures
python health_check.py --failing
```

Sample output:

```
[5] Online Khabar (https://www.onlinekhabar.com)
  Status      : ✓ OK
  Reachable   : True
  Links found : 18
  Title OK    : True
  Content OK  : True
```

---

## 🗄️ Database Schema

### `ecn.news_sites`

| Column | Type | Description |
|---|---|---|
| `id` | INT | Primary key |
| `name` | VARCHAR | Display name |
| `base_url` | VARCHAR | Homepage URL |
| `active` | TINYINT | 1 = scrape, 0 = skip |
| `is_priority` | TINYINT | 1 = always scrape, never auto-disable |
| `article_selector` | VARCHAR | CSS selector for article links |
| `title_selector` | VARCHAR | CSS selector for article title |
| `content_selector` | VARCHAR | CSS selector for article body |
| `failure_count` | INT | Consecutive failure counter |
| `last_error` | TEXT | Last error message |
| `last_scraped` | DATETIME | Timestamp of last successful scrape |

### `ecn.news_articles`

| Column | Type | Description |
|---|---|---|
| `id` | INT | Primary key |
| `title` | VARCHAR | Article headline |
| `link` | VARCHAR | Source URL (unique) |
| `content` | TEXT | Article body text |
| `category` | VARCHAR | Auto-detected category |
| `published_date` | DATETIME | Publication date (AD, Nepal time) |
| `date_source` | VARCHAR | Where the date was extracted from |
| `date_confidence` | ENUM | `high` / `medium` / `low` / `none` |
| `scraped_at` | DATETIME | When the scraper collected it |
| `is_read` | TINYINT | 0 = unread, 1 = read |
| `is_political` | ENUM | `Yes` / `No` |
| `is_election_related` | ENUM | `Yes` / `No` |
| `is_toxic` | ENUM | `Yes` / `No` |
| `content_hash` | CHAR(64) | SHA-256 hash for duplicate detection |
| `language` | VARCHAR | `ne` / `en` / `ne_en` |
| `source` | VARCHAR | Site name (matches `news_sites.name`) |
| `local_image_path` | VARCHAR | Downloaded thumbnail path |

### `ecn.scrape_runs`

| Column | Description |
|---|---|
| `started_at` | Run start timestamp |
| `sites_attempted` | Total sites in this run |
| `sites_failed` | Sites that returned 0 articles |
| `articles_saved` | Total articles saved |
| `duration_seconds` | How long the run took |

---

## 📅 Bikram Sambat Date Handling

Nepali news sites publish dates in the Bikram Sambat (BS) calendar. The scraper converts them to AD using an **anchor-based algorithm** rather than walking from the traditional 1943 epoch, which accumulates a 14-day error over 82 years.

**Verified anchor:** `BS 2082/01/01 = AD 2025-04-14`

The conversion is implemented in both Python (`utils/helpers.py`) and PHP (`news_list.php`) using the same anchor and the same BS month-length lookup table (BS 2000–2090).

### Date extraction pipeline

The scraper tries 8 sources in priority order:

1. JSON-LD `datePublished` / `dateCreated`
2. Meta tags (`article:published_time`, `pubdate`, etc.)
3. HTML `<time>` tags
4. CSS-selected date elements
5. BS calendar text scan in article content
6. Relative date phrases (e.g. "२ घण्टा अघि", "2 hours ago")
7. AD/Nepali text date patterns
8. ISO date regex fallback

**Future-time handling:** If a site's clock is ahead and the published time is in the future, the time component is stripped and only the date is stored — because a wrong time is more misleading than no time.

---

## 🔄 Automatic Selector Detection

When a site has no stored CSS selectors, `selector_detector.py` runs automatically:

1. **WordPress fingerprint** — detects WP themes (covers ~80% of Nepali news sites)
2. **Known CMS patterns** — Jeg, TD, MVP, and other popular themes used in Nepal
3. **Heuristic scoring** — scores candidate selectors by link density, article-like structure, and heading hierarchy

Selectors are saved to the database after first detection. If a selector breaks (returns 0 links), the scraper clears it and re-detects immediately without waiting for the next run.

---

## 📰 Dashboard (PHP)

The PHP dashboard (`news_list.php`) provides a full reading interface:

- Responsive card layout (1→2 column grid on wide screens)
- Filter by date, category, source, read status
- Bikram Sambat date display alongside AD dates
- Mark read / unread per article or all at once
- Deactivate a site directly from a news card
- Inactive sites management page (`inactive_sites.php`)
- Category and tag badges as clickable filters

---

## 🕐 Automated Scheduling

Run the scraper on a schedule with cron:

```bash
# Every 30 minutes
*/30 * * * * cd /path/to/news-scraper && python main.py >> logs/cron.log 2>&1

# Every hour, priority sites only (faster run)
0 * * * * cd /path/to/news-scraper && python main.py --workers 10 --latest 10 >> logs/cron.log 2>&1
```

---

## 📋 Logging

Logs are written to `logs/scraper_YYYY-MM-DD.log` and rotated daily. Retention is 14 days by default.

```
INFO  News Scraper starting
INFO    Workers    : 50
INFO    Max age    : 1 day(s)
INFO    Latest     : 20 articles/site
INFO    Mode       : ALL NEWS (keyword filter OFF)
INFO  ✓ [1/120] Online Khabar — 18 articles  (total: 18)
INFO  ✓ [2/120] Setopati — 14 articles  (total: 32)
...
INFO  Run complete — 847 articles from 120 sites in 42.3s  (3 sites with 0 articles)
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/new-site-support`
3. Add your changes and test with `health_check.py`
4. Submit a pull request

To add support for a new site with unusual structure, create a site-specific scraper in `scrapers/` following the pattern in `scrapers/ekantipur.py`.

---

## 📄 License

MIT License — see `LICENSE` for details.
